# ローカル認証（ユーザー名/パスワード）クイックスタート

## 概要

クラウドのOAuthプロバイダー（Google/GitHub等）なしで、完全にローカルで認証を使用できます。

## 特徴

✅ **完全ローカル**: インターネット接続不要、クラウドサービス不要  
✅ **簡単設定**: `.env`ファイルに1行追加するだけ  
✅ **柔軟**: 後でGoogle/GitHub認証に切り替え可能  
✅ **複数ユーザー**: カンマ区切りで複数ユーザー定義可能

---

## クイックスタート（3ステップ）

### ステップ1: 環境変数を設定

`.env`ファイルを作成または編集:

```bash
cd /Users/toku/workspace/projects/Decentralized-Agent-Kit
cp .env.example .env
```

`.env`を編集:

```bash
# NextAuth Secret (generate with: openssl rand -base64 32)
NEXTAUTH_SECRET=$(openssl rand -base64 32)

# ローカル認証ユーザー（username:password形式、カンマ区切り）
LOCAL_AUTH_USERS=admin:admin123,toku:mypassword,user:pass123

# 認証を必須にする（オプション）
REQUIRE_AUTH=true
NEXT_PUBLIC_REQUIRE_AUTH=true

# LLM設定（既存）
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-api-key
```

### ステップ2: 起動

```bash
docker compose up --build
```

### ステップ3: サインイン

1. ブラウザで `http://localhost:3000` を開く
2. サインイン画面が表示される
3. ユーザー名: `admin`, パスワード: `admin123` でサインイン
4. メッセージを送信してテスト

**完了！** 🎉

---

## ユーザーの追加/変更

### 複数ユーザーの定義

```bash
LOCAL_AUTH_USERS=admin:StrongPass123,toku:MySecure456,alice:AlicePass789
```

### 新しいユーザーを追加

1. `.env`を編集してユーザーを追加:
   ```bash
   LOCAL_AUTH_USERS=admin:admin123,newuser:newpass
   ```

2. 再起動:
   ```bash
   docker compose down
   docker compose up
   ```

### パスワード変更

1. `.env`でパスワードを変更:
   ```bash
   LOCAL_AUTH_USERS=admin:NewPassword123
   ```

2. 再起動

---

## 使い方

### サインイン

1. `http://localhost:3000` にアクセス
2. Username と Password を入力
3. "Sign In" ボタンをクリック

### サインアウト

画面右上の "Sign Out" ボタンをクリック

### 履歴管理

- 各ユーザーごとに会話履歴が保存されます
- サインアウトしても履歴は保持されます
- 同じユーザー名でサインインすれば履歴が復元されます

---

## 認証モードの組み合わせ

### パターン1: ローカル認証のみ（現在の設定）

```bash
LOCAL_AUTH_USERS=admin:admin123
# OAuth providerは設定しない
```

**サインイン画面**:
- ユーザー名/パスワードフォームのみ表示

### パターン2: ローカル + Google認証

```bash
LOCAL_AUTH_USERS=admin:admin123
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

**サインイン画面**:
- ユーザー名/パスワードフォーム
- "Or continue with" 区切り線
- "Sign in with Google" ボタン

ユーザーはどちらの方法でもサインイン可能！

### パターン3: ローカル + GitHub + Google

```bash
LOCAL_AUTH_USERS=admin:admin123
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=yyy
GITHUB_CLIENT_ID=zzz
GITHUB_CLIENT_SECRET=www
```

**サインイン画面**:
- ユーザー名/パスワードフォーム
- "Sign in with Google" ボタン
- "Sign in with GitHub" ボタン

---

## セキュリティのベストプラクティス

### ✅ 推奨

1. **強力なパスワードを使用**
   ```bash
   # ❌ 弱い
   LOCAL_AUTH_USERS=admin:admin
   
   # ✅ 強い
   LOCAL_AUTH_USERS=admin:Xy9$mK2p!vN8qL4z
   ```

2. **パスワード生成**
   ```bash
   # ランダムパスワード生成
   openssl rand -base64 12
   ```

3. **本番環境では`.env`をgitignore**
   - `.env`ファイルはgitにコミットしない
   - `.env.example`を参考用に用意

### ⚠️ 注意

1. **平文パスワード保存**
   - 現在の実装はパスワードを平文で`.env`に保存します
   - 小規模チーム/個人利用向け
   - 大規模/本番環境ではKeycloak等の検討を

2. **共有環境**
   - サーバーを複数人で共有する場合は注意
   - `.env`ファイルへのアクセス権限を制限

---

## トラブルシューティング

### "Invalid username or password" エラー

**原因**: ユーザー名またはパスワードが間違っている

**解決方法**:
1. `.env`の `LOCAL_AUTH_USERS` を確認
2. フォーマットが正しいか確認: `username:password,user2:pass2`
3. スペースが入っていないか確認

### サインインボタンが表示されない / フォームが表示されない

**原因**: 環境変数が正しく設定されていない

**解決方法**:
1. `.env`に `LOCAL_AUTH_USERS` が設定されているか確認
2. docker composeを再起動:
   ```bash
   docker compose down
   docker compose up --build
   ```
3. UIコンテナのログを確認:
   ```bash
   docker compose logs ui
   ```

### サインイン後にリダイレクトされない

**原因**: `NEXTAUTH_URL` が正しくない

**解決方法**:
`.env`を確認:
```bash
NEXTAUTH_URL=http://localhost:3000
```

### "Sign in failed" エラー

**原因**: `NEXTAUTH_SECRET` が設定されていない

**解決方法**:
```bash
# .envに追加
NEXTAUTH_SECRET=$(openssl rand -base64 32)
```

---

## Google/GitHub認証への切り替え

### ローカル認証を維持したまま追加

`.env`にOAuthプロバイダーの設定を追加するだけ:

```bash
# ローカル認証（既存）
LOCAL_AUTH_USERS=admin:admin123

# Google認証（追加）
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

→ ユーザーは**どちらの方法でもサインイン可能**

### ローカル認証を無効化

`.env`から `LOCAL_AUTH_USERS` を削除またはコメントアウト:

```bash
# LOCAL_AUTH_USERS=admin:admin123

# Google認証のみ有効
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

---

## まとめ

✅ **即座に使える**: クラウド設定不要、`.env`編集だけ  
✅ **シンプル**: `username:password` 形式で複数ユーザー管理  
✅ **柔軟**: Google/GitHub等との併用可能  
✅ **安全**: 認証必須モードで未認証アクセスをブロック  

小規模チームやローカル開発には最適な選択肢です！
