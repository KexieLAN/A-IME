local has_socket, socket = pcall(require, "socket")

-- ==========================================
-- 状态追踪 (用于纠错捕获)
-- ==========================================
local last_ai_word = nil            -- 上一次 AI 推荐的词
local last_pinyin = ""              -- 上一次的拼音
local notifier_connected = false    -- 是否已连接 RIME 通知器

-- ==========================================
-- 🛡️ 微服务级熔断器 (Circuit Breaker)
-- ==========================================
local backend_dead_until = 0
local CIRCUIT_BREAKER_COOLDOWN = 5

-- ==========================================
-- 纠错发送 (fire-and-forget, 100ms 超时)
-- ==========================================
local function send_correction(pinyin, correct_word)
  if not has_socket then return end

  local tcp = socket.tcp()
  tcp:settimeout(0.1)

  local ok, _ = tcp:connect("127.0.0.1", 5000)
  if not ok then
    tcp:close()
    return
  end

  local payload = string.format(
    '{"type":"correction","pinyin":"%s","correct_word":"%s"}',
    pinyin, correct_word
  )

  local req = "POST /rerank HTTP/1.1\r\n" ..
      "Host: 127.0.0.1:5000\r\n" ..
      "Content-Type: application/json; charset=utf-8\r\n" ..
      "Content-Length: " .. #payload .. "\r\n" ..
      "Connection: close\r\n\r\n" ..
      payload

  tcp:send(req)
  tcp:close()
end

-- ==========================================
-- RIME 通知器连接 (检测用户最终选词)
-- ==========================================
local function setup_notifier(env)
  if notifier_connected then return end
  notifier_connected = true

  -- 优先尝试 select_notifier: 用户选中候选词时触发，可获取精确选词
  local ok, _ = pcall(function()
    env.engine.context.select_notifier:connect(function(ctx)
      if last_ai_word then
        -- select_notifier 触发时，被选中的候选词已进入 preedit
        -- 此时 ctx.input 是剩余未上屏的拼音，无法直接获取选中词
        -- 因此仅清除追踪状态，不发送纠错（此 API 信息不足）
        last_ai_word = nil
      end
    end)
  end)

  if not ok then
    -- 回退到 commit_notifier: 文本上屏时触发
    pcall(function()
      env.engine.context.commit_notifier:connect(function(ctx)
        if last_ai_word then
          -- 获取上屏文本，检查是否包含 AI 推荐词
          local committed = ctx:get_commit_text() or ""
          -- 如果上屏文本中不包含 AI 推荐词，说明用户选择了其他词
          if not string.find(committed, last_ai_word, 1, true) then
            send_correction(last_pinyin, committed)
          end
          last_ai_word = nil
        end
      end)
    end)
  end
end

-- ==========================================
-- 主过滤器
-- ==========================================
local function candidate_collection(input, env)
  -- 连接通知器 (仅首次调用时执行)
  setup_notifier(env)

  local current_pinyin = env.engine.context.input or ""

  -- ==========================================
  -- 1. 懒加载截取首屏 (绝不榨干水龙头)
  -- ==========================================
  local context_cands = {}
  local cand_texts = {}
  local count = 0
  local MAX_FETCH = 5

  for cand in input:iter() do
    table.insert(context_cands, cand)
    if cand.type ~= "punct" and cand.type ~= "symbol" then
      table.insert(cand_texts, cand.text)
    end
    count = count + 1
    if count >= MAX_FETCH then
      break
    end
  end

  if count == 0 then return end

  -- 2. 检查熔断器状态
  local current_time = os.time()
  local is_backend_alive = current_time >= backend_dead_until

  -- 3. 网络通信部分
  local ai_generated_word = nil
  local ai_covered_length = 0
  local reranked_words = {}

  if has_socket and #cand_texts > 0 and string.len(current_pinyin) > 5 and is_backend_alive then
    local cand_json_array = '["' .. table.concat(cand_texts, '", "') .. '"]'

    local payload = string.format(
      '{"version_id": "%s_%s", "trigger_mode": "passive", "context": "等待Python接管", "pinyin": "%s", "candidates": %s}',
      tostring(os.clock()), current_pinyin, current_pinyin, cand_json_array
    )

    local tcp = socket.tcp()
    tcp:settimeout(0.2)

    local success, _ = tcp:connect("127.0.0.1", 5000)

    if success then
      local req = "POST /rerank HTTP/1.1\r\n" ..
          "Host: 127.0.0.1:5000\r\n" ..
          "Content-Type: application/json; charset=utf-8\r\n" ..
          "Content-Length: " .. string.len(payload) .. "\r\n" ..
          "Connection: close\r\n\r\n" ..
          payload

      tcp:send(req)

      local response, _, partial = tcp:receive("*a")
      local raw_data = response or partial

      if raw_data and string.len(raw_data) > 0 then
        local body = string.match(raw_data, "\r\n\r\n(.*)")
        if body then
          ai_generated_word = string.match(body, '"generated_word"%s*:%s*"([^"]+)"')
          local cl = string.match(body, '"covered_length"%s*:%s*(%d+)')
          if cl then
            ai_covered_length = tonumber(cl)
          end
          -- 解析 reranked_candidates 中的 word 字段
          for word in string.gmatch(body, '"word"%s*:%s*"([^"]+)"') do
            table.insert(reranked_words, word)
          end
        end
      end
      tcp:close()
    else
      backend_dead_until = current_time + CIRCUIT_BREAKER_COOLDOWN
    end
  end

  -- ==========================================
  -- 4. 候选词排序与渲染 (基于 logprobs 重排)
  -- ==========================================

  -- 构建原生候选词快速查找表
  local cand_map = {}
  for _, cand in ipairs(context_cands) do
    if not cand_map[cand.text] then
      cand_map[cand.text] = cand
    end
  end

  -- 【第一位】：绝对保底！永远输出四叶草原生词库的 Top 1
  local first_cand = context_cands[1]
  coroutine.yield(first_cand)
  local yielded = { [first_cand.text] = true }

  -- 判断 AI 推荐词是否来自 Phase2 (不在原生候选中)
  local ai_is_phase2 = false
  if ai_generated_word then
    ai_is_phase2 = (cand_map[ai_generated_word] == nil)
  end

  -- 【第二位】：Phase2 生成词 (不在原生候选中，带 🌟 标记注入)
  if ai_generated_word and ai_is_phase2 then
    local safe_start = context_cands[1].start
    local safe_end
    if ai_covered_length > 0 then
      local input_len = string.len(current_pinyin)
      safe_end = math.min(safe_start + ai_covered_length, input_len)
    else
      safe_end = context_cands[1]._end
    end
    if safe_end > safe_start then
      local gen_cand = Candidate(context_cands[1].type, safe_start, safe_end, ai_generated_word, " 🌟")
      coroutine.yield(gen_cand)
      yielded[ai_generated_word] = true
    end
  end

  -- 【重排区域】：按 reranked_candidates 顺序输出 (Phase1 推荐词在此自然插入)
  for _, word in ipairs(reranked_words) do
    if not yielded[word] and cand_map[word] then
      coroutine.yield(cand_map[word])
      yielded[word] = true
    end
  end

  -- 【补漏】：输出未被重排覆盖的原生候选词
  for _, cand in ipairs(context_cands) do
    if not yielded[cand.text] then
      coroutine.yield(cand)
      yielded[cand.text] = true
    end
  end

  -- 【剩余词库】：全量续放，翻页键完美工作
  for cand in input:iter() do
    coroutine.yield(cand)
  end

  -- ==========================================
  -- 5. 追踪状态 (用于纠错捕获)
  -- ==========================================
  if ai_generated_word then
    last_ai_word = ai_generated_word
    last_pinyin = current_pinyin
  end
end

return candidate_collection
