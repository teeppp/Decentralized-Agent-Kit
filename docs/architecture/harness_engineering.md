# ハーネスエンジニアリング（コンテキスト管理を中心に）

DAK を「長いタスクでも壊れないエージェントアプリ」にするための設計メモ。
Claude Code や LangChain Deep Agents との差分、ADK 標準機能との対応、実装済みの
コンテキストハーネス、残りのバックログをまとめる。

## 1. 発端: 1 リクエストでコンテキスト超過

「既存のバックログと実装を確認し、品質改善・ハーネスエンジニアリングを整理して」
という依頼を llama.cpp（Qwen 27B, `n_ctx=32768`）構成の DAK に送ると、1 回の
invocation の中で約 20 回のモデル呼び出し（ツールでファイルを読み進める）が
続いたあと、次のエラーで停止した。

```
request (41039 tokens) exceeds the available context size (32768 tokens)
```

### 根本原因

| # | 原因 | 詳細 |
|---|------|------|
| 1 | **既存の保護が死んでいた** | `AdaptiveAgent` は `session.contents` からトークン数を見積もっていたが、ADK の `Session` にあるのは `events` だけ。見積もりは常に 0 になり、「50% でモード切替＋履歴クリア」は一度も発火していなかった（テストは MagicMock で `contents` を差し込んでいたため通っていた）。 |
| 2 | **ツール出力に上限がない** | MCP の `read_file`/`run_command`/`list_files` はファイル全体や出力全体をそのまま返す。さらに ADK の MCP アダプタは FastMCP の `structuredContent` もそのまま渡すため、**同じテキストが 2 回**モデルに入る。 |
| 3 | **invocation 内で圧縮する仕組みがない** | ツールループは 1 invocation の中で履歴が伸び続ける。仮に 1 が動いていても、履歴を `clear()` するやり方は DB セッションに永続化されず、ツール呼び出しと応答のペアも壊しかねない。 |

## 2. ADK に Deep Agents 相当はあるか

**`create_deep_agent()` のような「全部入りハーネス」は ADK 2.8 には無い**。
ただし部品は揃っており、Deep Agents / Claude Code の各機能に対応するものがある。

| ハーネス機能 | Deep Agents / Claude Code | ADK 2.8 の部品 | DAK の状態 |
|---|---|---|---|
| コンテキスト圧縮 | 窓の 85% で要約、`compact_conversation` ツール / auto-compact | `App(events_compaction_config=EventsCompactionConfig(token_threshold=…, event_retention_size=…))`。2.x から **モデル呼び出し前**（invocation 内）にも効く。2.8.0 で見積もりにツール呼び出し・応答の文字数が入った | **採用（本変更）** |
| 大きなツール結果の退避 | 大きい結果をファイルへ退避してポインタを返す / Read の offset・limit | 標準機能なし（`after_tool_callback` プラグインと Artifact で組める） | **実装（本変更）**: `ContextHarnessPlugin` + `read_tool_output` |
| ファイル操作ツール | `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` | `EnvironmentToolset`（read/write/edit/execute）、`ExecuteBashTool` | MCP の read/write/list/run/search（名前検索のみ）。本変更で出力上限と行範囲読み込みを追加 |
| 計画 / TODO | `write_todos` | `PlanReActPlanner` / `BuiltInPlanner` | `planner`（確認必須・状態に残らない） |
| サブエージェント（コンテキスト分離） | `task` ツール | `AgentTool`（子エージェントを独立コンテキストで実行し結果だけ返す） | A2A peer のみ。調査用の分離サブエージェントは無し |
| スキル（段階的開示） | Skills | `SkillToolset`（list/search/load skill、resource、script） | 独自 `SkillRegistry` + `enable_skill` |
| ツール失敗からの回復 | リトライ / 自己修正 | `ReflectAndRetryToolPlugin` | `on_tool_error` で観測値化のみ |
| プロンプトキャッシュ | Anthropic cache | `ContextCacheConfig`（2.8 で Anthropic のキャッシュブレークポイント対応） | 未使用 |
| 中断・再開 | チェックポイント | `ResumabilityConfig` | 未使用 |
| ベンダ製ハーネスの取り込み | — | `google.adk.labs.antigravity.AntigravityAgent`（Antigravity SDK の harness を ADK ノードとして包む。labs 扱い・Gemini 前提） | 不採用（マルチプロバイダ/ローカル LLM という憲章と合わない） |

結論: 「ADK を更新するだけで Deep Agents 相当になる」わけではない。ただし一番効く
**コンテキスト圧縮は ADK 標準で取り込める**。そこで ADK を 2.4 → 2.8 に上げて
（2.9.0 は依存の最低経過日数ゲート〔safe-chain〕に掛かるため見送り）、その上に DAK 側の
ハーネスを薄く載せた。

## 3. 実装したコンテキストハーネス（`agent/dak_agent/harness.py`）

`agent.py` は `root_agent` に加えて ADK の `App` を公開し、`adk web`（A2A を含む）は
`app` のほうを優先して読み込む。安いものから順に 3 段で防ぐ。

1. **ツール出力の上限**（`ContextHarnessPlugin.after_tool_callback`）
   - 上限を超えた結果は先頭 70% と末尾 30% のプレビューに置き換え、全文は Artifact
     （`tool_output_<tool>_<call_id>.txt`）へ退避する。エージェントは
     `read_tool_output(artifact_name, offset, limit, pattern)` で続きを読んだり、
     正規表現で絞り込んだりできる。
   - MCP 結果で `structuredContent` が本文の複製になっている場合は落とす（全 MCP 呼び出しで
     約半分の節約になる）。
2. **ADK の token-threshold compaction**（`EventsCompactionConfig`）
   - 直近のプロンプトが窓の 60% を超えたら、モデルを呼ぶ前に古いイベントを要約して
     置き換える。直近 4 イベントはそのまま残し、関数呼び出しと応答のペアは ADK が壊さない。
   - 要約プロンプトは「元の依頼の原文、調べ済みのファイルと事実、決定事項、残作業」を
     残すよう DAK 用に調整した。
3. **リクエストガード**（`ContextHarnessPlugin.before_model_callback`）
   - ADK は圧縮した要約を **model ロール**のメッセージとして差し込む。そのため元の依頼まで
     圧縮されると、リクエストにユーザーの発話が 1 つも残らない。llama.cpp の Qwen テンプレート
     （`--jinja`）はこれを `No user query found in messages` で拒否する（実機で確認。
     Anthropic も先頭がユーザーであることを要求する）。そこでユーザーの text ターンが
     無いときは、「以下の要約から作業を続けて」という短いユーザーターンを先頭に補う。
   - 組み立て後のリクエストが窓の 85% を超える場合、古いツール応答から順に
     `[elided …]` に差し替える。ADK はセッションの Content をそのまま使うため、
     オブジェクトは書き換えずに差し替える。
   - 見積もりは **CJK を 1 文字 = 1 トークン**で数える。単純な `len // 4` では日本語で
     3〜4 倍の過小評価になる。

加えて:
- mcp-server: `read_file(path, offset, limit)`（行範囲）を追加し、`read_file`/`run_command` は
  `MCP_MAX_OUTPUT_CHARS`（既定 50K 文字）、`list_files`/`search_files` は `MCP_MAX_LIST_ENTRIES`
  （既定 500 件）で打ち切って、続きの取り方を示すようにした。
- `ModeManager`: トークン閾値トリガを削除した（圧縮はハーネスの担当）。モード切替は
  `switch_mode` 呼び出し時のみ行い、履歴は消さない。Meta-LLM プロンプトが存在しない
  `switch_mode(request_tool_list=True)` を指示していた不具合も直した。

### 設定（環境変数）

予算はすべてモデルのコンテキスト窓から算出する（`MODEL_CONTEXT_WINDOW`、無ければ
LiteLLM のモデルマップ、それも無ければ 128K）。

| 変数 | 既定 | 意味 |
|---|---|---|
| `DAK_CONTEXT_HARNESS` | `true` | `false` でハーネス全体を無効化 |
| `DAK_COMPACTION_THRESHOLD_RATIO` | `0.6` | 圧縮を始める窓占有率 |
| `DAK_COMPACTION_RETAIN_EVENTS` | `4` | 圧縮せずに残す直近イベント数 |
| `DAK_COMPACTION_INTERVAL` | `20` | sliding-window 圧縮の間隔（ユーザーターン数） |
| `DAK_REQUEST_BUDGET_RATIO` | `0.85` | 最終ガードの上限 |
| `DAK_TOOL_OUTPUT_MAX_CHARS` | 窓の 15%（2K〜40K 文字） | 1 回のツール結果の上限 |

目安: 8K 窓 → 圧縮 4,915 tok / ツール出力 2,000 文字。32K 窓 → 19,660 tok / 4,915 文字。
1M 窓 → ツール出力 40,000 文字。

### 検証

- `agent/tests/test_harness.py` の E2E テストは、実際の ADK `Runner` と台本どおりに動く
  モデル（8K 窓）で「1 invocation の中で巨大なツール結果を 6 回受け取る」状況を再現する。
  ハーネスなしでは 2 回目のリクエストが 38K トークンになって失敗し、ハーネスありでは
  リクエストが最大 6.2K トークン、圧縮 2 回で最後まで完走することを検証している。
  台本モデルは、ユーザーの発話が無いリクエストを Qwen テンプレートと同じように拒否するので、
  上記のガードも同じテストで検証される。
- 実機（llama-server + Qwen 27B, 32K）で元の依頼を再実行し、ツール出力の切り詰め
  （例: `read_file` 14,947 → 4,915 文字）と invocation 内での圧縮が働くことを確認した。
- 1 の不具合を再発させないため、`AdaptiveAgent` のテストは `session.events` を使う形に改めた。

## 4. 残りのギャップとバックログ（優先度順）

各項目は GitHub Issue 化して Project (DAK Sustainability) で管理している。

| 優先 | 項目 | 狙い | 関連 |
|---|---|---|---|
| P1 | **調査用サブエージェント（`AgentTool`）** | 「リポジトリを読んで要約」を子エージェントに任せ、親のコンテキストには結論だけを残す（Deep Agents の `task`、Claude Code の Explore 相当）。長い調査タスクで最も効く | #85 |
| P1 | **内容検索ツール（grep）と行番号付き読み込み** | 今の `search_files` はファイル名しか検索できず、中身を探すにはファイル全体を読むしかない。`grep(pattern, path, glob)` と `edit_file`（文字列置換）を足すか、ADK `EnvironmentToolset` への移行を検討 | #86, #16, #20 |
| P1 | **TODO ツール（セッション state に保存）** | `write_todos` 相当。圧縮後も計画が消えないよう state に置き、指示へ注入する。今の `planner` は `require_confirmation=True` のため、「計画を立てる」だけで毎回承認待ちになり、A2A や `/run` 経由の自律実行が止まる（実機で確認。本変更で承認は opt-in 化済み） | #87, #21 |
| P2 | **コンテキスト超過からの回復** | `on_model_error_callback` で `ContextWindowExceededError` を受けたら、強制圧縮して再試行するか、利用者に分かる形で失敗させる | #88 |
| P2 | **窓サイズの自動検出** | llama-server の `/props`（`n_ctx`）から窓を取る。compose 既定の 8192 と実サーバーの 32768 のようなずれを防ぐ | #89 |
| P2 | **`SkillToolset` への移行** | 独自の `SkillRegistry`/`enable_skill` を ADK 標準（Agent Skills 仕様・段階的開示・リソース読み込み）に寄せ、保守コストを下げる | #90, #81 |
| P2 | **ツール失敗の自己修正** | `ReflectAndRetryToolPlugin` を試す | #91 |
| P2 | **モード切替の整理** | 圧縮とスキルで役割の多くが代替されたので、Meta-LLM によるモード切替を残すかどうかを評価で判断する（動的ツール削減 #81 と合わせて検討） | #92, #81 |
| P3 | **長時間タスクの評価** | nightly-eval に「リポジトリ調査」系の長いゴールデンシナリオを加え、窓超過率・圧縮回数・トークン数を Langfuse の指標で追う | #93, #5, #71 |
| P3 | **プロンプトキャッシュ** | `ContextCacheConfig`（Gemini/Anthropic）でコストと遅延を下げる | #94 |
| P3 | **サンドボックス** | ファイル・コマンド系ツールの分離 | #20, #31, #43, #80 |
