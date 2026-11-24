import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { buildReference, type ApiReference, type ApiSchema } from "@/lib/openapi";

/**
 * A ```openapi fenced block (YAML or JSON), drawn as an API reference:
 * the API's title and servers, then every operation grouped by tag, each
 * foldable, with its parameters, request body and responses as tables.
 *
 * The YAML parser is imported dynamically, like mermaid in MermaidDiagram:
 * only a page that holds such a block downloads it. Everything the document
 * says is shown as TEXT -- descriptions are not rendered as Markdown or HTML,
 * so a pasted spec cannot put markup on the page.
 *
 * `render-pending` while parsing, so the print view (pages/PrintBook.tsx)
 * waits for it like it waits for diagrams.
 */
export function OpenApiReference({ source }: { source: string }) {
  const { t } = useI18n();
  const [state, setState] = useState<{ api?: ApiReference; error?: string } | null>(null);

  useEffect(() => {
    let live = true;
    setState(null);
    const handle = window.setTimeout(() => {
      const text = source.trim();
      const parse: Promise<unknown> = text.startsWith("{")
        ? Promise.resolve().then(() => JSON.parse(text))
        : import("yaml").then((yaml) => yaml.parse(text, { maxAliasCount: 100 }));
      parse
        .then((doc) => buildReference(doc))
        .then((api) => live && setState({ api }))
        .catch((err: unknown) => live && setState({ error: err instanceof Error ? err.message : String(err) }));
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(handle);
    };
  }, [source]);

  if (!state) return <div className="render-pending openapi-loading">{t("openapi.loading")}</div>;
  if (state.error || !state.api) {
    return (
      <div className="callout callout-warning" role="note">
        <p className="callout-title">{t("openapi.error")}</p>
        <p className="font-mono text-xs">{state.error}</p>
      </div>
    );
  }
  const api = state.api;
  return (
    <section className="openapi not-prose">
      {(api.title || api.version) && (
        <p className="openapi-title">
          {api.title} {api.version && <span className="openapi-version">{api.version}</span>}
        </p>
      )}
      {api.description && <p className="openapi-text">{api.description}</p>}
      {api.servers.length > 0 && (
        <p className="openapi-servers">
          {t("openapi.servers")}{" "}
          {api.servers.map((s, i) => (
            <code key={i}>{s}</code>
          ))}
        </p>
      )}
      {api.groups.map((group) => (
        <div key={group.name || "_"} className="openapi-group">
          {group.name && <p className="openapi-tag">{group.name}</p>}
          {group.description && <p className="openapi-text">{group.description}</p>}
          {group.operations.map((op) => (
            <details key={op.id} id={op.id} className={`openapi-op openapi-${op.method.toLowerCase()}`}>
              <summary>
                <span className="openapi-method">{op.method}</span>
                <code className="openapi-path">{op.path}</code>
                <span className="openapi-summary">{op.summary}</span>
                {op.deprecated && <span className="openapi-deprecated">{t("openapi.deprecated")}</span>}
              </summary>
              <div className="openapi-body">
                {op.description && <p className="openapi-text">{op.description}</p>}
                {op.parameters.length > 0 && (
                  <>
                    <p className="openapi-heading">{t("openapi.parameters")}</p>
                    <table>
                      <thead>
                        <tr>
                          <th>{t("openapi.name")}</th>
                          <th>{t("openapi.in")}</th>
                          <th>{t("openapi.type")}</th>
                          <th>{t("openapi.description")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {op.parameters.map((p) => (
                          <tr key={`${p.in}:${p.name}`}>
                            <td>
                              <code>{p.name}</code>
                              {p.required && <span className="openapi-required"> *</span>}
                            </td>
                            <td>{p.in}</td>
                            <td>{p.type}</td>
                            <td>{p.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
                {op.body && (
                  <>
                    <p className="openapi-heading">
                      {t("openapi.body")} {op.body.contentType && <code>{op.body.contentType}</code>}
                      {op.body.required && <span className="openapi-required"> *</span>}
                    </p>
                    {op.body.description && <p className="openapi-text">{op.body.description}</p>}
                    <SchemaTable schema={op.body.schema} />
                  </>
                )}
                {op.responses.length > 0 && (
                  <>
                    <p className="openapi-heading">{t("openapi.responses")}</p>
                    {op.responses.map((r) => (
                      <div key={r.status} className="openapi-response">
                        <p>
                          <span className={`openapi-status openapi-status-${r.status[0]}`}>{r.status}</span> {r.description}
                          {r.contentType && <code className="ml-2">{r.contentType}</code>}
                        </p>
                        <SchemaTable schema={r.schema} />
                      </div>
                    ))}
                  </>
                )}
              </div>
            </details>
          ))}
        </div>
      ))}
      <p className="openapi-legend">{t("openapi.legend")}</p>
    </section>
  );
}

function SchemaTable({ schema }: { schema: ApiSchema | null }) {
  const { t } = useI18n();
  if (!schema) return null;
  if (!schema.fields.length) return <p className="openapi-text"><code>{schema.type}</code></p>;
  return (
    <table>
      <thead>
        <tr>
          <th>{t("openapi.field")}</th>
          <th>{t("openapi.type")}</th>
          <th>{t("openapi.description")}</th>
        </tr>
      </thead>
      <tbody>
        {schema.fields.map((f) => (
          <tr key={f.name}>
            <td style={{ paddingLeft: `${0.5 + f.depth * 1}rem` }}>
              <code>{f.name}</code>
              {f.required && <span className="openapi-required"> *</span>}
            </td>
            <td>{f.type}</td>
            <td>{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
