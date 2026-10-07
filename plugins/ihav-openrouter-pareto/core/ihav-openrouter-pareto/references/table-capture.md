# Table step: read openrouter.ai/models in Table view

Python has no browser. The skill reads the Table with the host's browser tool and hands the text to `ingest`.
The API has no Weekly Tokens, Latency or Throughput; this step is the only source for them and for the displayed
price labels ("from $0.04", "N% off"). Do not use cookies, do not log in, do not type credentials.

## Steps for one modality

1. Open the modality's URL from `config.json` `table_urls` (for example
   `https://openrouter.ai/models?order=top-weekly&output_modalities=image`).
2. Switch the page to its **Table** view. Check that one `<table>` exists and its header contains `Weekly Tokens`.
3. Note the row count the page shows for the modality (the count on the modality tab, for example "Image 59").
   This is `--expected-rows`. If the page shows no count, stop and report it; do not count the rows yourself.
4. Run the script below in the page. It returns the text contract. If the tool cuts long output, return
   `lines.slice(a, b).join('\n')` in chunks of 200 lines and append them in order; `ingest` checks the row count.
5. Write the text to `.ihav_space/ihav-openrouter-pareto/captures/<capture_id>/table_<modality>.txt`.
6. Run `ingest --capture <capture_id> --modality <modality> --file <that file> --url <page URL>
   --expected-rows <count> --captured-at <ISO time you read the table> --view table`.
   `"complete": false` (exit code 3) means rows are missing or a cell no longer parses: report rows read vs expected
   and the first errors. Do not edit the text to make it pass.

## Text contract

- One line `# Columns: slug|<header cells in page order>`; an empty header cell is written `(empty)`.
- Then one line per `tbody tr`: the model slug from the row's two-segment model link (`/openai/gpt-image-2`,
  including any `:free` or `:batch` suffix), then every cell's text, joined with `|`.
- A cell with `colspan` n is written once with `{n}` appended (`from $0.04{2}`); later cells shift left.
- `—` means missing. Weekly tokens look like `4.03B`; latency `163ms`, `29.0s`, `1m 4s`; throughput `80 t/s`.
- Other `#` lines are comments.

```js
(() => {
  const table = document.querySelector('table');
  const clean = (s) => s.replace(/\s+/g, ' ').trim().replace(/\|/g, '/');
  const heads = [...table.querySelectorAll('thead th')].map((th) => clean(th.textContent) || '(empty)');
  const lines = ['# Columns: slug|' + heads.join('|')];
  for (const tr of table.querySelectorAll('tbody tr')) {
    const link = [...tr.querySelectorAll('a[href]')].find((a) => new URL(a.href).pathname.split('/').filter(Boolean).length === 2);
    const slug = link ? decodeURIComponent(new URL(link.href).pathname.slice(1)) : '';
    const cells = [...tr.children].map((td) => clean(td.textContent) + (td.colSpan > 1 ? '{' + td.colSpan + '}' : ''));
    lines.push([slug, ...cells].join('|'));
  }
  return lines.join('\n');
})()
```

The unfiltered page (`table_urls.all`, every modality in one table) may be ingested as `--modality all`; a file
without a `# Columns:` line needs `--columns`, for example `--columns "index|slug|Weekly Tokens|Latency|Throughput"`.

Whether a visitor who is not logged in sees every column is not yet known (the 2026-10-07 fixtures were read in the
admin's Chrome, and whether that session was logged in was not checked). If columns are missing, say so; the API-only views still work.
