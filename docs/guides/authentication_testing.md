# 認証ありの動作確認方法

## 前提条件

認証機能をテストするには、少なくとも1つのOAuthプロバイダーを設定する必要があります。
最も簡単なのは **Google OAuth** です。

---

## ステップ1: Google OAuthの設定

### 1.1 Google Cloud Consoleでプロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 新しいプロジェクトを作成（または既存のプロジェクトを選択）
3. プロジェクト名: `DAK Agent Test` など

### 1.2 OAuth同意画面の設定

1. 左メニューから **APIs & Services** → **OAuth consent screen** を選択
2. **User Type**: `External` を選択して `CREATE`
3. 以下を入力:
   - **App name**: `DAK Agent`
   - **User support email**: あなたのメールアドレス
   - **Developer contact information**: あなたのメールアドレス
4. `SAVE AND CONTINUE` をクリック
5. Scopes画面: そのまま `SAVE AND CONTINUE`
6. Test users画面: `+ ADD USERS` であなたのGoogleアカウントを追加
7. `SAVE AND CONTINUE` → `BACK TO DASHBOARD`

### 1.3 OAuth 2.0 認証情報の作成

1. 左メニューから **Credentials** を選択
2. `+ CREATE CREDENTIALS` → `OAuth client ID` を選択
3. **Application type**: `Web application`
4. **Name**: `DAK Agent Web Client`
5. **Authorized JavaScript origins** の `+ ADD URI`:
   ```
   http://localhost:3000
   ```
6. **Authorized redirect URIs** の `+ ADD URI`:
   ```
   http://localhost:3000/api/auth/callback/google
   ```
7. `CREATE` をクリック
8. 表示される **Client ID** と **Client secret** をコピー

---

## ステップ2: 環境変数の設定

### 2.1 ルートの `.env` ファイルを作成

```bash
cd /Users/toku/workspace/projects/Decentralized-Agent-Kit
cp .env.example .env
```

### 2.2 `.env` を編集

```bash
# NextAuth Secret (generate with: openssl rand -base64 32)
NEXTAUTH_SECRET=your-generated-secret-here

# Google OAuth (Step 1.3でコピーした値)
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-client-secret

# 認証必須モード（テスト用にtrueに設定）
REQUIRE_AUTH=true
NEXT_PUBLIC_REQUIRE_AUTH=true

# LLM設定（既存）
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-gemini-api-key
```

**重要**: `NEXTAUTH_SECRET` を生成:
```bash
openssl rand -base64 32
```

---

## ステップ3: アプリケーションの起動

### 3.1 既存のコンテナを停止（実行中の場合）

ターミナルで `Ctrl+C` を押して停止、または:
```bash
docker compose down
```

### 3.2 再ビルドして起動

```bash
docker compose up --build
```

起動に1-2分かかります。以下のログが表示されれば成功:
```
ui-1          | ▲ Next.js 16.0.3
ui-1          | - Local:        http://localhost:3000
agent-1       | INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## ステップ4: 認証なし動作の確認

### 4.1 ブラウザでアクセス

`http://localhost:3000` を開く

### 4.2 期待される表示

- ✅ "Sign In" ボタンが表示される
- ✅ "⚠️ Authentication required" の警告が表示される
- ✅ 入力フォームが **無効化** されている（グレーアウト）
- ✅ ボタンのテキストが "Sign In Required" になっている

### 4.3 メッセージを送ろうとする

フォームは無効化されているため、何も入力できません。

これが **認証必須モード** の動作です。

---

## ステップ5: 認証あり動作の確認

### 5.1 サインイン

1. "Sign In" ボタンをクリック
2. "Sign in with Google" を選択
3. Googleアカウントを選択（テストユーザーとして追加したアカウント）
4. 権限の許可画面が表示されたら `Continue` をクリック

### 5.2 認証後の表示確認

サインインに成功すると:
- ✅ "Signed in as <あなたのメールアドレス>" と表示される
- ✅ "Sign Out" ボタンが表示される
- ✅ 入力フォームが **有効化** される
- ✅ ボタンのテキストが "Send Task" になる

### 5.3 メッセージを送信

1. 入力フォームに `Hello, what is your name?` と入力
2. "Send Task" ボタンをクリック
3. Agent Responseが表示されることを確認

### 5.4 ターミナルログの確認

Agentコンテナのログを確認:
```
agent-1  | API: UserID=<Google固有のID>, SessionID=session_<ID>, Auth=Header
```

**Auth=Header** となっていれば、認証されたユーザーIDが使われています。

### 5.5 履歴の確認

1. 別のメッセージを送信: `My name is Toku`
2. さらに別のメッセージ: `What is my name?`
3. Agentが "Toku" と答えることを確認

これで **ユーザー固有の履歴管理** が機能していることが確認できます。

---

## ステップ6: サインアウトの確認

### 6.1 サインアウト

"Sign Out" ボタンをクリック

### 6.2 期待される動作

- ✅ "Sign In" ボタンが再表示される
- ✅ フォームが再び無効化される
- ✅ 認証必須の警告が表示される

---

## ステップ7: 認証なしモードの確認

### 7.1 `.env` を編集

```bash
REQUIRE_AUTH=false
NEXT_PUBLIC_REQUIRE_AUTH=false
```

### 7.2 再起動

```bash
docker compose down
docker compose up --build
```

### 7.3 確認

1. `http://localhost:3000` にアクセス
2. ✅ サインインしなくても入力フォームが使える
3. ✅ メッセージを送信できる
4. ✅ ログには `Auth=Debug` と表示される

---

## ステップ8: API直接呼び出しの確認（オプション）

### 8.1 認証必須モード + ヘッダー認証

`.env` で `REQUIRE_AUTH=true` に設定している状態で:

```bash
# 認証なし（失敗する）
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'

# 期待される応答: {"detail":"Authentication required. Please provide valid credentials."}
```

```bash
# ヘッダー認証あり（成功する）
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test_user" \
  -H "X-Session-ID: test_session" \
  -d '{"prompt": "Hello"}'

# 期待される応答: {"response":"..."}
```

### 8.2 認証なしモード

`.env` で `REQUIRE_AUTH=false` に設定している状態で:

```bash
# 認証なしでも成功する
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'

# 期待される応答: {"response":"..."}
```

---

## トラブルシューティング

### "Sign in failed" エラー

**原因**: OAuth設定が正しくない

**解決方法**:
1. Google Cloud Consoleで **Authorized redirect URIs** を確認:
   ```
   http://localhost:3000/api/auth/callback/google
   ```
   末尾のスラッシュなど、一致しているか確認

2. `.env` の `GOOGLE_CLIENT_ID` と `GOOGLE_CLIENT_SECRET` が正しいか確認

3. ブラウザのコンソール（F12）でエラーメッセージを確認

### "This app is blocked" エラー

**原因**: OAuth同意画面でアプリが未承認

**解決方法**:
1. Google Cloud Console → **OAuth consent screen**
2. **Publishing status** を "Testing" のままにする
3. **Test users** にあなたのGoogleアカウントを追加

### NextAuth Error: `JWT_SESSION_ERROR`

**原因**: `NEXTAUTH_SECRET` が設定されていない、または一致していない

**解決方法**:
1. `.env` で `NEXTAUTH_SECRET` が設定されているか確認
2. `openssl rand -base64 32` で新しいシークレットを生成
3. docker-compose を再起動

### UIで "Sign In" ボタンが表示されない

**原因**: SessionProviderがマウントされていない可能性

**解決方法**:
1. ブラウザで `http://localhost:3000` のページをリロード
2. ブラウザのコンソール（F12）でエラーを確認
3. UIコンテナのログを確認: `docker compose logs ui`

---

## まとめ

✅ **認証必須モード**: `REQUIRE_AUTH=true` で認証なしアクセスをブロック  
✅ **認証なしモード**: `REQUIRE_AUTH=false` でデバッグ用に自由にアクセス可能  
✅ **柔軟な認証**: UI（OAuth）、API（ヘッダー）、デバッグの3モードをサポート  
✅ **ユーザー分離**: 認証されたユーザーごとに履歴が管理される
