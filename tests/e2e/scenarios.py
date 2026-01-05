from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Step:
    user_input: str
    expected_response_keyword: Optional[str] = None

@dataclass
class Scenario:
    id: str
    name: str
    description: str
    steps: List[Step]

SCENARIOS = [
    Scenario(
        id="01",
        name="基本会話 (Basic Chat)",
        description="ユーザーが挨拶し、エージェントが応答する",
        steps=[
            Step(user_input="こんにちは", expected_response_keyword="こんにちは")
        ]
    ),
    Scenario(
        id="02",
        name="ツール実行 (Tool Execution)",
        description="check_solana_balance を直接呼び出す",
        steps=[
            Step(user_input="Solanaウォレットの残高を確認して", expected_response_keyword="1000")
        ]
    ),
    Scenario(
        id="03",
        name="A2A通信 (A2A Comm)",
        description="ConsumerからProviderへメッセージ送信",
        steps=[
            Step(user_input="agent_providerに挨拶して", expected_response_keyword="agent_provider")
        ]
    ),
    Scenario(
        id="04",
        name="AP2 支払いフロー (AP2 Flow)",
        description="Premium分析を依頼 -> 支払い要求 -> 承認 -> 完了",
        steps=[
            Step(user_input="agent_providerにAI技術のプレミアム分析を依頼して。必要なら支払って。", expected_response_keyword="Payment Required"),
            Step(user_input="はい、10 SOLの支払いを承認します。", expected_response_keyword="PREMIUM ANALYSIS REPORT")
        ]
    ),
    Scenario(
        id="05",
        name="支払い拒否 (Payment Refusal)",
        description="Premium分析を依頼 -> 支払い要求 -> 拒否",
        steps=[
            Step(user_input="agent_providerにAI技術のプレミアム分析を依頼して。必要なら支払って。", expected_response_keyword="Payment Required"),
            Step(user_input="いいえ、支払いません。", expected_response_keyword="キャンセル")
        ]
    ),
    # Note: Scenario 06 requires changing mock balance, which is hard via E2E without restarting container. 
    # Skipping for now or implementing via specific env var if possible.
    
    Scenario(
        id="07",
        name="モード切替 (Mode Switch)",
        description="Enforcerモードへ切り替え",
        steps=[
            Step(user_input="Enforcerモードに切り替えて", expected_response_keyword="Enforcerモードに切り替えました")
        ]
    ),
    Scenario(
        id="08",
        name="無効なツール (Invalid Tool)",
        description="存在しないツールを要求",
        steps=[
            Step(user_input="存在しないツール 'super_tool' を実行して", expected_response_keyword="does not exist")
        ]
    ),
    Scenario(
        id="09",
        name="セッション維持 (Session)",
        description="文脈依存の質問",
        steps=[
            Step(user_input="私の名前はTokuです", expected_response_keyword="Toku"),
            Step(user_input="私の名前は何ですか？", expected_response_keyword="Toku")
        ]
    ),
    Scenario(
        id="10",
        name="LangFuse ログ確認",
        description="これはRunnerによって自動的に検証されます",
        steps=[
            Step(user_input="Langfuseのテストです", expected_response_keyword="Langfuse")
        ]
    )
]
