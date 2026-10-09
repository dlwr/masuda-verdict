# masuda-verdict

はてな匿名ダイアリーの人気エントリー（50 users 以上）を「創作（釣り・ネタを含む）」か「事実」かで判定し、本文だけを読んだモデルの判定とブコメ民意を並べる。

- GitHub Actions が6時間おきに人気エントリーを収集し、はてブ登録から48時間経ったものを判定する
- 本文判定: Cloudflare Workers AI の Clef。`TYPESAFE_API_KEY` / `OPENAI_API_KEY` があれば Jev / OpenAI Decisions も並べる
- ブコメ判定: 各コメントを Clef で「創作・事実・言及なし」に分類
- 判定結果は `data/` に JSONL で追記する。ブコメ本文と増田本文は保存しない
- サイトは `site/`（Astro）を GitHub Pages に置く
- 任意の増田 URL の判定は `worker/`（Cloudflare Worker、`/api/judge?url=`）。本文とブコメ最新50件を Clef で判定する。IP ごとと全体でレート制限あり

## 開発

```sh
mise install
uv sync
uv run pytest
uv run python -m masuda_verdict collect    # 人気エントリーを data/seen に記録
uv run python -m masuda_verdict judge      # CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN が必要
uv run python -m masuda_verdict aggregate  # site/src/data/summary.json を生成

cd site && pnpm install && pnpm dev
cd worker && pnpm install && pnpm test
```

Workers AI の無料枠（10,000 neurons/日）を超えると判定が途中で止まり、残りは次の実行に持ち越される。
