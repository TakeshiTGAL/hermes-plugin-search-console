# search-console-checkup for Hermes Agent

A weekly SEO check of your own site for [Hermes Agent](https://github.com/NousResearch/hermes-agent), built on the Google Search Console API.
Every Monday Hermes sends you what changed since last week and **the 3 fixes worth doing first**, not a wall of numbers.

**日本語の説明は[下にあります](#日本語)。**

- **Weekly check, unattended.** It runs as a script-only Hermes cron job: no LLM tokens, no browser sign-in, the same output every time. It is delivered to Telegram, Slack, Discord, e-mail or any other Hermes channel.
- **Compares only finished days.** Google keeps updating the last 2-3 days. The plugin asks Google which days are final, leaves the rest out, and says so in the report. A half-processed weekend never looks like a traffic drop.
- **Three fixes, ranked by clicks at stake.** Pages that fell out of Google's index and cost clicks come first. After them: titles that get seen but not clicked, queries that dropped, and queries just short of page 1. Each fix names the page, shows the evidence and says what to change.
- **Works for small sites and Japanese sites.** Small sites see most of their clicks under anonymised queries, so pages are analysed as well as queries. Query spellings that differ only in full-width/half-width characters or spacing are merged. URL moves such as `/guide` → `/guide.html` are not reported as lost pages. The report is in Japanese when the site's searches are.
- **Read-only, your own key.** A Google service-account key that you add to your property. The plugin itself talks only to Google.

```text
Search Console weekly check: sc-domain:example.jp
Compared Sep 23–Sep 29 with Sep 16–Sep 22 (Search Console days, US Pacific time).
Sep 30–Oct 2 still being processed by Google, so left out of the comparison.

Overall: clicks −5% vs the previous period. Most worth doing: Get a page back into Google's index.
Clicks 285 (−16, −5%) · Impressions 4,137 (+156, +4%) · CTR 6.9% · Avg position 6.1 (was 5.8; lower is better)
28.4% of clicks came from anonymised queries (Search Console does not show them one by one).

■ Next 3 fixes
1. Get a page back into Google's index
   https://example.jp/old-campaign/ had 80 impressions in the earlier period and none now. URL Inspection: excluded by a noindex tag or header.
   Unless you removed it on purpose, open the page in Search Console's URL Inspection, fix the reason it gives (noindex, canonical, robots.txt, 404…), then press Request indexing.
   Rough upside: +5 clicks per week.
2. Rewrite a title and description
   "パン 作り方 初心者" sits at position 4.1 with 300 impressions but a 0.3% CTR (this site usually gets 4.3% there).
   Put what people searching "パン 作り方 初心者" want near the start of the title of https://example.jp/guide/hajimete/, …
3. Recover a query that dropped
   "天然酵母 起こし方" went from position 5.2 to 9.5 (clicks 12 → 4). …

■ Queries and pages that dropped …   ■ More impressions, no more clicks …   ■ Indexing …   ■ Top pages / queries …
```
<sub>Sample from the test fixture (made-up site and numbers).</sub>

## Setup

You need a Search Console property you own or manage, and a Google account that can open the [Google Cloud console](https://console.cloud.google.com/). The Search Console API is free.

**In Google Cloud (once, about 5 minutes)**

1. Pick or create a project (top bar → project picker → **New project**).
2. **APIs & Services → Library** → search **Google Search Console API** → **Enable**.
3. **IAM & Admin → Service accounts → Create service account**. Any name, e.g. `hermes-search-console`, then **Done**. It needs no roles.
4. Open the new service account → **Keys → Add key → Create new key → JSON**. A `.json` file downloads. Copy the account's e-mail address (`…@….iam.gserviceaccount.com`).

**In Search Console**

5. Open your property → **Settings → Users and permissions → Add user**. Paste the service account's e-mail, choose permission **Full**, then **Add**. Full is needed for URL Inspection: Google's permission table limits Restricted users to "fetch only" there. The key can still change nothing, because the plugin asks Google for read-only access (`webmasters.readonly`). With Restricted, the performance part works, and pages that left the index are listed without the reason.

**In a terminal on the Hermes machine.** Replace the two marked parts: the downloaded file name and your property.

```bash
mkdir -p ~/.hermes/keys
mv ~/Downloads/YOUR-KEY-FILE.json ~/.hermes/keys/search-console.json   # ← the file name you downloaded
chmod 600 ~/.hermes/keys/search-console.json
hermes plugins install TakeshiTGAL/hermes-plugin-search-console --enable
#   → when asked for GSC_CREDENTIALS_FILE, type:  ~/.hermes/keys/search-console.json
#   → if asked about Python dependencies (google-auth, requests), answer yes
hermes search-console-checkup doctor sc-domain:example.com             # ← your property
```

To try a local copy instead of the GitHub repository, run `hermes plugins install "file://$PWD" --enable` inside a clone of this repository.

**If Hermes runs on another machine (a VPS),** the key is on your PC, so the order changes. Use these lines instead of the `mkdir` and `mv` lines above:

```bash
ssh user@server 'mkdir -p ~/.hermes/keys'                                                    # 1. on your PC
scp ~/Downloads/YOUR-KEY-FILE.json user@server:~/.hermes/keys/search-console.json            # 2. on your PC
```

Then log in to the server and run the rest there: the `chmod` line, `hermes plugins install …` and `hermes search-console-checkup doctor …`.

`doctor` reads the key, warns if other users on the machine can read the key file, lists the properties it can see, and checks the last 10 days to find the last finished day. If something is missing, it says exactly which screen to open.

Property names: a Domain property is `sc-domain:example.com`. A URL-prefix property is the full URL with a trailing slash, `https://www.example.com/`. You can also just pass `example.com`; the plugin matches it to the property.

## Every week, automatically

```bash
hermes search-console-checkup schedule sc-domain:example.com --deliver telegram
# It prints one line like the next one. Run it:
hermes cron create '0 9 * * 1' --no-agent --script search-console-weekly-domain-example-com.py --deliver telegram --name 'Search Console weekly: sc-domain:example.com'
```

This is a **script-only** job: Hermes runs the check and delivers the text as is. It uses no model and no tokens, and it never waits for a person. If the check fails (expired key, permission removed), the failure and what to do arrive in the same channel. `--when` takes any cron schedule (default Mondays 09:00 in Hermes's time zone). `--deliver` takes any Hermes target (`telegram`, `slack`, `discord:#seo`, `email`, `local`, …). Test it once with `hermes cron run <job id>`. To stop it, run `hermes cron remove <job id>` (`hermes cron list` shows the id) and delete the script from `$HERMES_HOME/scripts/`. Removing the plugin does not remove the job.

Two things Hermes needs for this, as for any cron job: the **gateway** must be running (`hermes gateway install` sets it up as a service; `hermes cron status` shows whether a scheduler is serving your jobs), and the delivery target must be connected (for `telegram`, the Telegram integration with its home channel). With `--deliver local` the report is saved under `~/.hermes/cron/output/`.

You can also just ask in chat: *"Every Monday at 9, run gsc_weekly_report for sc-domain:example.com and send me its message."* Hermes then creates an LLM cron job, which costs a model call per run.

In any chat with Hermes, `/gsc` (or `/gsc audit example.com`) returns the report directly, without a model call.

## Tools

| Tool | What it answers |
|---|---|
| `gsc_weekly_report` | Last 7 finished days vs the 7 before: 3 fixes, rank drops, more-impressions-no-more-clicks, index problems, sitemap errors, top pages and queries, plus a ready-to-send `message`. |
| `gsc_audit` | The same over 28 days (7-90), plus striking distance (positions 8-20), cannibalisation, decaying pages, winners, and the site's CTR-by-position curve. |
| `gsc_rank_changes` | Winners, losers (by clicks lost), new and lost queries or pages between two periods. Can split around a date you give. |
| `gsc_query` | Raw rows for any dimensions, filters, dates and search type, for questions the others do not answer. |
| `gsc_inspect_url` | Is this page indexed, and if not, why: noindex, robots.txt, canonical, fetch result, last crawl. |
| `gsc_sites` | Which properties the key can read, and as whom. |

Bundled skills: `search-console-checkup:seo-audit` and `search-console-checkup:rank-tracking` (load with `skill_view`).
CLI: `hermes search-console-checkup doctor|weekly|audit|schedule`. Settings (Desktop → Plugins, or `config.yaml` under `plugins.entries.search-console-checkup.settings`): `default_site`, and `language` (`auto`, `en`, `ja`). With `auto`, the report is Japanese when 30% or more of the site's impressions are on Japanese queries. Failure alerts from the weekly job use the language chosen when you ran `schedule` (with `auto`, from the site's searches at that time). Other error messages are Japanese for `.jp` properties or a Japanese system locale.

## How the data is handled

- **Unfinished days.** Each comparison asks Google with `dataState: all` which date is the first unfinished one (`metadata.firstIncompleteDate`). Windows end the day before it and use `dataState: final`. The excluded days are named in the report. If Google gives no answer, the last 3 days are left out and the report says so.
- **Time zone.** Search Console days are US Pacific time days. Windows are always whole days, and both windows of a comparison have the same weekdays.
- **Anonymised queries.** Google hides rare queries. Query rows therefore add up to less than the site total. The report shows the hidden share. Page-level analysis covers what query rows cannot see.
- **Spellings.** Query rows are merged after NFKC normalisation and whitespace folding (`食パン　レシピ` = `食パン レシピ`, `ﾚｼﾋﾟ` = `レシピ`). Page URLs that differ only in `http/https`, `www`, a trailing slash, `.html` or `index.html` are merged. A page that moved to a different path is checked with URL Inspection. If Google now uses the new URL and it gets impressions, the report says "moved, fine". Percent-encoded Japanese URLs are shown decoded.
- **What counts as a fix.** CTR is judged against the site's own CTR at the same position, learned from its data. When the site has too little data for that, the fixed rule "position ≤ 5 and CTR < 2%" is used. A gap only counts when the usual CTR would have produced at least 3 clicks; otherwise zero clicks is ordinary chance. A fix needs at least 2 clicks at stake per period. A page that left Google's index goes to the top only when it cost at least 2 clicks; otherwise it stays in the Indexing list. When fewer than three fixes pass these tests, the report says so instead of padding the list.
- **"Rough upside"** is impressions × (usual CTR − current CTR), or the clicks lost, per period. Striking-distance estimates are discounted by 75% because moving up takes work. It ranks the fixes against each other. It is not a forecast.
- **Limits.** Search Console keeps 16 months. Up to 100,000 rows are read per request type, and the report says when there were more. The weekly check uses about 13 API requests, including up to 3 URL Inspections. The URL Inspection quota is 2,000 per property per day.
- **Out of scope.** Bing Webmaster Tools data, Google Analytics 4, and third-party keyword or backlink estimates. For GA4 in Hermes, see the markifact plugin.

## What the plugin does on your machine (disclosure)

- **Network:** the plugin sends HTTPS requests only to `www.googleapis.com/webmasters/v3`, `searchconsole.googleapis.com/v1/urlInspection` and Google's OAuth token endpoint. All are read requests; the service account gets the `webmasters.readonly` scope. No telemetry. When you call the tools in a chat, the results become part of that conversation, which Hermes sends to your model provider like any tool result. The script-only weekly job uses no model; its text goes only to the delivery target you chose.
- **Reads:** the key file named by `GSC_CREDENTIALS_FILE`, nothing else.
- **Writes:** only `hermes search-console-checkup schedule` writes a file. It is one script in `$HERMES_HOME/scripts/`. The script records two absolute paths, the plugin directory and the key file (not the key itself), because Hermes starts cron scripts with a cleaned environment. Delete it to undo. Tokens are kept in memory only.
- **No background processes, no shell commands, no browser.** Every request has a 30-second timeout and at most two short retries. Under cron and the messaging gateway, nothing waits for a person.

### Optional: OAuth instead of a service account

`GSC_CREDENTIALS_FILE` may also point to an OAuth **authorized_user** file (`"type": "authorized_user"` with `client_id`, `client_secret`, `refresh_token`) made with **your own** OAuth client. One way: create an OAuth client of type *Desktop app* in your Google Cloud project, download its `client_secret_….json`, then run `gcloud auth application-default login --client-id-file=client_secret_….json --scopes=https://www.googleapis.com/auth/webmasters.readonly`. **Copy** the resulting `application_default_credentials.json` to its own path and point the variable there. Files made with gcloud's built-in clients (`application-default login` without `--client-id-file`, or the `adc.json` that `gcloud auth login` keeps) are refused (rule 11). The plugin refreshes the access token in memory and never writes the file. Tokens from an OAuth app left in "Testing" status expire after 7 days, which breaks unattended runs. A service account does not expire, so it remains the recommended choice.

## Troubleshooting

| `error` | Meaning and fix |
|---|---|
| `not_configured` | `GSC_CREDENTIALS_FILE` is not set: `hermes config set GSC_CREDENTIALS_FILE ~/.hermes/keys/search-console.json`. |
| `key_file_missing` / `key_file_unreadable` | The path is wrong, or the file is not the downloaded JSON key (or the key inside it is damaged). |
| `oauth_client_file` | You pointed at `client_secret_*.json`. That is an OAuth *client*, not a key. Use the service-account key. |
| `oauth_shared_client` | Files made with gcloud's built-in clients (`application-default login` without `--client-id-file`, or the `adc.json` that `gcloud auth login` keeps) are refused (rule 11). Use a service-account key, or make the file with your own client (see above). |
| `api_disabled` | Enable **Google Search Console API** in the key's project (APIs & Services → Library). |
| `no_access` | Add the key's e-mail in Search Console → Settings → Users and permissions. The error lists the properties the key *can* read. |
| `auth_failed` | The key was deleted or disabled, the clock is wrong, or an OAuth token expired. |
| "Create new key" is greyed out or refused | Your Google Workspace organisation enforces the policy `iam.disableServiceAccountKeyCreation` (often on by default in newer organisations). Ask the Workspace admin for an exception for this project, or use the OAuth option. |
| URL Inspection not allowed | Give the key **Full** permission in Search Console. The performance part keeps working meanwhile. |
| URL Inspection daily quota | 2,000 inspections per property per day; the rest are checked on the next run. |

## How this compares

The structure follows [open-seo-mcp-skills](https://github.com/Ryze-AI-Adgent/open-seo-mcp-skills) by Ryze AI (MIT): one job per tool, the same audit lenses (CTR anomalies, striking distance 8-20, decaying pages, cannibalisation, winners / losers / new / lost, losers ranked by clicks lost), and the verdict-first output. The differences are below.

| | open-seo-mcp-skills (read at `81ac50e`) | This plugin |
|---|---|---|
| Where the data comes from | The hosted Ryze connector: sign in to a Ryze workspace and connect your Google accounts there | Google's Search Console API directly, with your own key; no third-party account |
| What is installed | Markdown skills; the model follows the steps and does the arithmetic | Code that computes the results the same way every time, plus 2 skills |
| Weekly report | The rank-tracking skill suggests scheduling it with the host's scheduler | Built in: a script-only Hermes cron job delivered to your messaging channel, no model call |
| Output | Tables per lens + a 5-item action list | Verdict, then **3 fixes ranked by clicks at stake**, then short lists that fit one chat message |
| Unfinished days | "GSC lags ~2 days — never include today" | Asks Google which day is the first unfinished one, excludes it and says so |
| CTR anomaly rule | Fixed: position ≤ 5 and CTR < 2% | Against the site's own CTR at that position (the fixed rule is the fallback); chance-level gaps ignored |
| Anonymised queries | Not mentioned | Reports the hidden share; page-level fixes are ranked with query-level ones |
| Site moves, `.html`, `www`, `https` | Not mentioned in the skills | URL spellings merged before comparing; moves to a new path confirmed "moved, fine" by URL Inspection |
| Japanese | Not mentioned in the skills | Full-width and half-width spellings merged; report and errors in Japanese |
| GA4, ads, DataForSEO, backlinks | Yes (through Ryze) | No. Search Console only. |

Also read, for good ideas: [mcp-gsc](https://github.com/AminForou/mcp-gsc) (MIT), [mcp-server-gsc](https://github.com/ahonn/mcp-server-gsc) (MIT), [marketingskills `seo-audit`](https://github.com/coreyhaines31/marketingskills) (MIT). See [NOTICE](NOTICE).

## Development

```bash
python -m venv .venv && .venv/bin/pip install "google-auth>=2.20,<3" "requests>=2.31,<3" pytest
.venv/bin/python -m pytest          # offline, on recorded API responses (tests/fixtures)
hermes plugins validate . --install-deps
```

The fixtures keep the response shapes recorded from the live API. All values in them are made up.

## License

MIT. See [LICENSE](LICENSE) and, for adapted material, [NOTICE](NOTICE).

---

## 日本語

Google Search Console API を活用した、自分のサイトの毎週の SEO 点検です。自社サイトの Search Console のデータを、Hermes が直接読みます。毎週月曜に「先週から何が変わったか」と「先に直すべき3件」を、Telegram・Slack・メールなどへ送ります。数字を並べるのではなく、直す相手（ページ・語）と、その根拠と、何を変えるかを書きます。

### できること

- 毎週の点検を自動で送ります。LLM を使わない定期実行なので、トークン代がかからず、毎回同じ基準で出ます。人の操作も待ちません。
- Google がまだ集計中の直近2〜3日は比較から外し、外した日をレポートに書きます。集計途中の週末が「急落」に見えることはありません。
- 次の候補から3件に絞ります。インデックスから外れてクリックを失ったページ、表示は多いのにクリックされないタイトル、順位が落ちた語、あと一歩で1ページ目に届く語。並び順は「取り戻せそうなクリック数」です。
- 小さなサイトと日本語のサイトで使えます。小さなサイトではクリックの大半が匿名化された語から来るため、ページ単位でも分析します。全角・半角・スペースだけが違う語はまとめます。`/guide` → `/guide.html` のような移転は「消えたページ」と数えません。日本語の URL は読める形で表示します。検索の3割以上が日本語なら、レポートも日本語になります。

### 導入

**Google Cloud で（最初の1回、5分ほど）**

1. 画面上部のプロジェクト選択で、プロジェクトを選ぶか「新しいプロジェクト」を作る。
2. 「API とサービス」→「ライブラリ」→ **Google Search Console API** を検索 →「有効にする」。
3. 「IAM と管理」→「サービス アカウント」→「サービス アカウントを作成」。名前は任意（例: `hermes-search-console`）で「完了」。ロールは不要です。
4. 作ったアカウントを開き、「鍵」→「鍵を追加」→「新しい鍵を作成」→「JSON」。`.json` ファイルがダウンロードされます。アカウントのメールアドレス（`…@….iam.gserviceaccount.com`）を控えます。

**Search Console で**

5. 対象のプロパティを開き、「設定」→「ユーザーと権限」→「ユーザーを追加」。控えたメールアドレスを貼り、権限は **フル** を選んで「追加」。
   - 「フル」が要るのは URL 検査（インデックスから外れた理由の確認）のためです。Google の権限表では、「制限付き」は URL 検査が「取得のみ」に限られています。
   - プラグインは Google に読み取り専用の許可（`webmasters.readonly`）しか求めないので、この鍵でサイトの設定が変わることはありません。
   - 「制限付き」でも数字の点検は動きます。その場合、消えたページは理由なしで一覧に出ます。

**Hermes を動かしているマシンのターミナルで**

次をそのまま貼ります。`← ここを変える` と書いた2か所だけ、自分のファイル名とプロパティに置き換えてください。

```bash
mkdir -p ~/.hermes/keys
mv ~/Downloads/YOUR-KEY-FILE.json ~/.hermes/keys/search-console.json   # ← ここを変える（ダウンロードしたファイル名）
chmod 600 ~/.hermes/keys/search-console.json
hermes plugins install TakeshiTGAL/hermes-plugin-search-console --enable
#   → GSC_CREDENTIALS_FILE を聞かれたら  ~/.hermes/keys/search-console.json  と入力
#   → Python の依存（google-auth, requests）を入れてよいか聞かれたら yes
hermes search-console-checkup doctor sc-domain:example.com             # ← ここを変える（自分のプロパティ）
```

- 手元のコピーで試すときは、clone したフォルダで `hermes plugins install "file://$PWD" --enable` を実行します。

- Hermes が別のマシン（VPS など）で動いている場合は、鍵が手元の PC にあるので順番が変わります。上の `mkdir` と `mv` の2行の代わりに、手元の PC で次の2行を実行します（`user@server` は自分のサーバーに変える）。
  ```bash
  ssh user@server 'mkdir -p ~/.hermes/keys'                                               # 1. 手元の PC で
  scp ~/Downloads/YOUR-KEY-FILE.json user@server:~/.hermes/keys/search-console.json       # 2. 手元の PC で
  ```
  そのあとサーバーにログインし、残りの `chmod`・`hermes plugins install …`・`hermes search-console-checkup doctor …` をサーバーで実行します。
- プロパティ名の形:
  - ドメイン プロパティは `sc-domain:example.com`
  - URL プレフィックス プロパティは `https://www.example.com/`（末尾の `/` まで含む）
  - `example.com` とだけ書いても、該当するプロパティを探します。
- `doctor` が「準備できました」と出れば完了です。鍵ファイルをほかのユーザーも読める状態なら、`chmod 600` を促す警告も出します。足りないものがあれば、開く画面の名前つきで知らせます。

### 毎週の自動点検

```bash
hermes search-console-checkup schedule sc-domain:example.com --deliver telegram   # ← プロパティと送り先を変える
# 表示された「hermes cron create …」の1行を、そのまま実行する
```

- 届けるには、Hermes の gateway（常駐プロセス）が動いていることと、送り先（Telegram など）がつながっていることが必要です。どの定期実行でも同じ条件です。
  - 未設定なら `hermes gateway install` で常駐させます。
  - 動いているかは `hermes cron status` で確かめられます。
- 送り先の例: `telegram`、`slack`、`email`。`local` にすると `~/.hermes/cron/output/` に保存します。
- 曜日と時刻は `--when` で変えられます（初期値は月曜9時。時刻は Hermes に設定したタイムゾーン）。
- 失敗したとき（鍵の期限切れ、権限の取り消しなど）は、何をすればよいかを書いた通知が同じ送り先に届きます。
- 止めるときは `hermes cron remove <ジョブ ID>`（ID は `hermes cron list` で分かります）を実行し、`$HERMES_HOME/scripts/` のスクリプトを消します。プラグインを外してもジョブは残ります。
- チャットで `/gsc` と送れば、その場で同じレポートが返ります。

### データの扱い

- 日付は Search Console の仕様どおり、米国太平洋時間の日です。比べる2つの期間は曜日をそろえます。
- 匿名化された語の割合をレポートに出します。語として見えない分は、ページ単位の分析で補います。
- 直す候補にするのは、偶然ではない差だけです。普段のクリック率なら3回以上クリックされたはずの語・ページを対象にし、見込みが2クリック未満のものは挙げません。
- インデックスから外れたページは、クリックを失っているときだけ先頭に置きます。意図して外したページなら対応は要りません。
- 「見込み +N クリック」は、候補同士を比べるための目安です。予測ではありません。
- 扱わないもの: Bing、GA4、他社の推定データ（キーワード量・被リンク）。

### プラグインがすること・しないこと

- 通信するのは Google の Search Console API と、Google のトークン発行先だけです。読み取りしかしません。
- チャットでツールを使うと、その結果は会話の一部としてモデルの提供元に送られます（ほかのツールと同じ）。
- 毎週の自動点検はモデルを使わず、結果は指定した送り先にだけ届きます。
- 読むファイルは鍵ファイルだけです。
- 書くファイルは `schedule` が作る1本のスクリプトだけです（置き場所は `$HERMES_HOME/scripts/`）。中身は鍵ファイルとプラグインの場所（パス）で、鍵そのものは入りません。

### 困ったとき

エラーには必ず「対処」が付きます。開く画面の名前まで書いてあります。よくあるものは次のとおりです。

- 権限のエラー（`no_access`）: 鍵のメールアドレスを Search Console の「ユーザーと権限」に追加してください。
- 「新しい鍵を作成」が押せない: Google Workspace の組織ポリシーで鍵の作成が禁止されています（新しい組織では既定で有効なことが多い）。Workspace の管理者にこのプロジェクトだけ例外にしてもらうか、OAuth の方法（英語節の Optional: OAuth）を使ってください。
- URL 検査だけ断られる: 権限を「フル」にしてください。数字の点検はその間も動きます。
