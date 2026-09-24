# 呼び出しごとの設定（`dak:` キー）

1 つの DAK を複数の用途で使い分けるために、呼び出し元は 1 回の呼び出しごとに
指示や出力の形を渡せる。何も渡さなければ、今までどおり起動時の設定で動く。
実装は `agent/dak_agent/call_config.py`（受け口と検証）と
`agent/dak_agent/adaptive_agent.py`（適用）。

## 渡し方

| 経路 | 置き場所 |
|---|---|
| ADK の `/run` / `/run_sse` | リクエストの `state_delta` |
| A2A | message の `metadata`（ADK が `RunConfig.custom_metadata["a2a_metadata"]` に入れる） |

`/run` の例:

```json
{
  "app_name": "dak_agent",
  "user_id": "u1",
  "session_id": "s1",
  "new_message": {"role": "user", "parts": [{"text": "来週の京都 2 泊の旅程を作って"}]},
  "state_delta": {
    "dak:instruction": "あなたは旅程を作る。出力は JSON だけ。",
    "dak:output_schema": {
      "type": "object",
      "required": ["days"],
      "properties": {"days": {"type": "array", "items": {"type": "string"}}}
    }
  }
}
```

## キー

| キー | 値 | 指定しないとき |
|---|---|---|
| `dak:instruction` | 文字列。そのセッションのシステムプロンプトになる（既定の指示・モード指示・スキルの追記を置き換える） | `AGENT_INSTRUCTION`（とモード・スキル）のまま |
| `dak:output_schema` | JSON Schema（dict、Draft 2020-12）。LLM のリクエストに構造化出力の指定（`response_schema`、`response_mime_type=application/json`）が入り、最終応答はこのスキーマで検証される | 指定なし。今までどおりの自由形式の応答 |
| `dak:model` | LiteLLM のモデル ID（例: `bedrock/openai.gpt-5.6-luna`、`openai/gpt-5.6-luna`）。その呼び出しの LLM リクエストだけがこのモデルに向かう。運用者が `DAK_ALLOWED_MODELS` で許可したものだけ使える | `MODEL_NAME` のまま |

- `dak:instruction` の文字列はそのまま LLM に届く。ADK の `{名前}` 差し込み（セッション state の値で置き換える機能）は通さないので、`{date}` のような文字を含めてよい
- ADK は指示の後ろに、自分の識別行（`You are an agent. Your internal name is "dak_agent".`）を足す。これは既定の指示でも同じ

## モデルの許可一覧（運用者）

`dak:model` で選べるモデルは、運用者が環境変数 `DAK_ALLOWED_MODELS`（カンマ区切りのモデル ID）で決める。
呼び出し元が任意のモデルを指定して、費用の上限を破れないようにするため。

- **未設定なら、`dak:model` の指定は常に拒否する。** 許可するときだけ、運用者が明示的に設定する
- 一覧に無いモデル（または文字列でない値）を指定すると、LLM を一切呼ばずに、そのターンは次の応答で終わる

```json
{"error": "model_not_allowed", "requested_model": "openai/not-allowed", "allowed_models": ["openai/fake-alt", "openai/fake-default"]}
```

- モデルの別名（短い名前の辞書）は無い。`MODEL_NAME` と同じ形のモデル ID をそのまま書く
- 1 回のリクエストの上限（コンテキストハーネスの `request_token_budget`）は、選んだモデルのコンテキスト窓（LiteLLM のモデル表）から計算し直す。`MODEL_CONTEXT_WINDOW` は起動時の `MODEL_NAME` の窓なので、ほかのモデルには使わない。LiteLLM のモデル表に無いモデル（llama-server の別名など）は窓が分からないので、起動時のモデルの窓（`MODEL_CONTEXT_WINDOW` があればその値）を使う。窓の小さいローカルモデルを許可一覧に入れるときは、既定モデルもそれ以下の窓にしておく
- 履歴の圧縮（ADK の compaction）が始まるトークン数は、起動時の `MODEL_NAME` の窓で決まったまま変わらない（App を作るときに 1 度だけ決まるため）

## 効く範囲と優先順位

- `state_delta` で渡した値はセッション state に書かれる。そのため、**同じセッションの以降の呼び出しにも効く**。別のセッションには効かない。解除するには、同じキーに `null` を渡す
- A2A の metadata で渡した値は、その呼び出しだけに効く（state には書かれない）
- 両方にあるときは、セッション state の値が勝つ（state > A2A metadata > `custom_metadata`）。1 つのセッションで 2 つの経路を混ぜないこと

## 応答がスキーマに合わないとき

最終応答（ツール呼び出しを含まないテキスト）が `dak:output_schema` に合わなければ、DAK はその応答を次の JSON に差し替えて返す。
再試行はしない（検査と再試行は #140 の範囲）。

```json
{
  "error": "output_schema_validation_failed",
  "issues": [
    {"path": "date", "message": "'date' is a required property"},
    {"path": "trip/days", "message": "'three' is not of type 'integer'"}
  ]
}
```

- `path` は不正な値の位置を `/` でつないだもの。必須の項目が無いときは、その項目の名前で終わる
- JSON として読めない応答は `{"path": "", "message": "invalid JSON: ..."}`
- スキーマ自体が正しくないときは `{"path": "", "message": "invalid output_schema: ..."}`
- `$ref` はスキーマの中（`#/$defs/...`）と、JSON Schema 標準のメタスキーマだけを解決する。`http://...` などの外部の参照は取りに行かない（呼び出し元のスキーマで、agent コンテナから任意の URL へリクエストさせないため）。解決できない参照は `invalid output_schema` になる
- `{}`（何でも受け付けるスキーマ）を渡しても、応答が JSON であることは確かめる

## 検証しているテスト

- `agent/tests/test_call_scoped_instruction.py` — 指示がそのセッションのシステムプロンプトだけになる。並行する別セッションは既定のまま
- `agent/tests/test_call_scoped_output_schema.py` — リクエストに構造化出力の指定が入る。合わない応答が構造化された失敗になる
- `tests/integration/test_call_config_flow.py` — 実際の構成（agent コンテナ → LiteLLM → fake-LLM）で同じことを確かめる
