# llama.cpp で実LLMスモークを回す

Ollama（`scripts/smoke_local_llm.sh`）に加えて、**llama.cpp の `llama-server`** でも
実LLMスモークを実行できる。llama-server は OpenAI 互換の `/v1` を話すので、
エージェント側は fake-LLM と同じ `openai/` プロバイダのまま接続先を替えるだけ
（`docker-compose.llamacpp.yml`）。

**設計方針: サーバは GPU のある場所で動かし、動かすのは「トンネル」であって
コードではない。** クライアント（compose スタック）は常にホストのポート
`18080` を見る。サーバが手元にあるか、Colab にあるか、LAN の GPU サーバに
あるかは SSH フォワードで吸収する。

```bash
# サーバがどこかで立っている前提で:
./scripts/smoke_llamacpp.sh            # :18080 を確認 → スタック起動 → スモーク実行
LLAMACPP_PORT=8080 ./scripts/smoke_llamacpp.sh
```

## マシン別セットアップ

### A. この Mac（Metal）

```bash
brew install llama.cpp
llama-server -hf bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M \
             --port 18080 --jinja -c 8192
```

- **`--jinja` は必須**: chat template を有効化しないと OpenAI 形式の
  tool calling（structured `tool_calls`）が出ない。
- モデルは Ollama スモークで検証済みの llama3.1 8B 系を既定にする
  （tool-calling の信頼性が確認済み。詳細は README のモデル比較表）。
  Q4_K_M で ~4.9GB。
- **16GB Mac の注意**: 8B Q4 は動くが、より大きいモデルはスワップ膨張で
  ディスクを食い潰すことがある（別プロジェクトで実害あり）。空き容量に注意。

### B. Google Colab GPU（google-colab-cli + SSH フォワード）

Colab の GPU VM 上で llama-server を動かし、ローカルの `18080` にフォワードする。
ノートブックは使わない。

```bash
uv tool install git+https://github.com/googlecolab/google-colab-cli.git
colab new -s local-llm --gpu G4      # コンピューティングユニットを消費する点に注意
colab ssh -s local-llm               # ~/.ssh/config に Host エントリを書く
# VM 側: モデル取得と llama-server 起動（VM のシェルで）
#   llama-server -hf <model.gguf> --port 18080 -ngl 99 --jinja
# ローカル側: フォワードを維持
ssh -N colab-llm                     # LocalForward 18080 が開く
curl http://127.0.0.1:18080/health   # 確認
./scripts/smoke_llamacpp.sh
```

### C. Ubuntu GPU サーバ（LAN / SSH トンネル）

サーバ側で llama-server（CUDA ビルド, `-ngl 99 --jinja`）を 8080 などで起動し、
ローカルへトンネルする:

```bash
ssh -N -L 18080:localhost:8080 <gpu-host> &
./scripts/smoke_llamacpp.sh
```

**Linux ホストで compose スタックを動かす場合の注意**: 素の Docker Engine では
`host.docker.internal` は bridge ゲートウェイ IP（例 172.17.0.1）に解決されるため、
**127.0.0.1 にバインドされたリスナーにはコンテナから到達できない**（`ssh -L` も
llama-server も既定はループバックバインド）。ホストの `curl localhost:18080` は
通るのにコンテナが全部 connection refused になったらこれ。
`ssh -N -L 0.0.0.0:18080:localhost:8080 <gpu-host>`（または llama-server 側を
`--host 0.0.0.0` で起動）にする。macOS / Docker Desktop では不要。
同じ失敗クラスの前例: `docker-compose.local-llm.yml` のコメントと
`nightly-eval.yml` の `OLLAMA_HOST=0.0.0.0`。

## モデル選択の指針

README の Ollama モデル比較表と同じ結論がそのまま当てはまる:
**ここでの選択基準はサイズや新しさではなく tool-calling の信頼性**。

- ✅ llama3.1 8B 系: 多ツール提示でも structured tool calls を安定して出す
- ⚠️ thinking 系（qwen3 等）: `<think>` がターンの 120s タイムアウトを圧迫
- ❌ tool call を生 JSON テキストで出すモデル: ReAct ループが壊れる

新しいモデルを試すときは、まず `./scripts/smoke_llamacpp.sh` の 4 テストが
通るかで判定し、通ったら `tests/integration/tools/capture_golden.py` で
golden 化して決定論スイートに還元する（`docs/eval/README.md` のループ）。

## CI での利用について

GitHub Actions の無料ランナーは CPU のみで、nightly-eval は既に Ollama を
使っている。llama.cpp を CI に載せる価値が出るのは GPU 付き self-hosted
runner（Ubuntu GPU サーバ）を導入する場合 — これは別 Issue で検討。
その際はセクション C の Linux ループバックバインドの注意が必ず該当する。
