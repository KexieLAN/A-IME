import flask
from flask import Flask, request, jsonify
import json
import time

app = Flask(__name__)


@app.route("/rerank", methods=["POST"])
def rerank():
    # 1. 提取 Lua 发送过来的 JSON 数据
    # silent=True 保证即使 Lua 发来的不是完美 JSON 也不直接崩溃，方便我们排错
    data = request.get_json(silent=True)

    if data is None:
        print(f"{time.time():.3f}[警告] 收到请求，但解析 JSON 失败！可能是 Lua 端发出的 Header 或格式有误。")
        return jsonify({
            "error": "Invalid JSON"
        }), 400

    print("\n" + "🚀 " + "=" * 45)
    print(f"📥 [收到 Lua 请求] 耗时记录点: {time.time():.3f}")
    print("-" * 50)
    print(json.dumps(data, indent=4, ensure_ascii=False))
    print("=" * 50 + "\n")

    mock_response = {
        "version_id": data.get("version_id", "unknown_version"),
        "status": "success",
        "generated_word": None,
        "reranked_candidates": []
    }

    return jsonify(mock_response), 200


if __name__ == "__main__":
    print("🟢 Flask 回显靶机已启动！")
    print("📡 正在监听: http://127.0.0.1:5000/rerank")
    print("👀 等待接收 Lua 拦截的数据...")

    # debug=True 可以在你修改代码后自动重启服务
    app.run(host='127.0.0.1', port=5000, debug=True)
