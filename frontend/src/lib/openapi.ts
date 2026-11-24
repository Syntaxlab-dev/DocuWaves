/**
 * An OpenAPI 3.x (or Swagger 2.0) document, boiled down to what an API
 * reference page shows: operations grouped by tag, each with its
 * parameters, request body and responses, and every schema as a list of
 * fields. Pure data in, pure data out; components/OpenApiReference.tsx
 * draws it, and parses YAML before handing it here.
 *
 * Only LOCAL references (`#/components/...`, `#/definitions/...`) are
 * followed. A reference to another file or URL is shown by name: a docs
 * page must not fetch arbitrary addresses while someone reads it. Cycles
 * and very deep schemas stop at MAX_DEPTH with the name of the schema.
 */

export const METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"] as const;
const MAX_DEPTH = 4;
const MAX_FIELDS = 200;

type Json = unknown;
type Obj = Record<string, Json>;

export interface ApiField {
  /** Dotted path below the schema root, "[]" for array items: "items[].id". */
  name: string;
  type: string;
  required: boolean;
  description: string;
  depth: number;
}

export interface ApiSchema {
  /** The schema's own type, e.g. "object", "array of Pet", "string (uuid)". */
  type: string;
  fields: ApiField[];
}

export interface ApiParameter {
  name: string;
  in: string;
  type: string;
  required: boolean;
  description: string;
}

export interface ApiBody {
  contentType: string;
  description: string;
  required: boolean;
  schema: ApiSchema | null;
}

export interface ApiResponse {
  status: string;
  description: string;
  contentType: string;
  schema: ApiSchema | null;
}

export interface ApiOperation {
  id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  deprecated: boolean;
  parameters: ApiParameter[];
  body: ApiBody | null;
  responses: ApiResponse[];
}

export interface ApiGroup {
  name: string;
  description: string;
  operations: ApiOperation[];
}

export interface ApiReference {
  title: string;
  version: string;
  description: string;
  servers: string[];
  groups: ApiGroup[];
}

const isObj = (v: Json): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: Json): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");

function refName(ref: string): string {
  return ref.split("/").pop() ?? ref;
}

function makeResolver(root: Obj) {
  return function resolve(value: Json, seen: string[] = []): { value: Obj; name: string; cycle: boolean } {
    if (!isObj(value)) return { value: {}, name: "", cycle: false };
    const ref = value.$ref;
    if (typeof ref !== "string") return { value, name: "", cycle: false };
    const name = refName(ref);
    if (!ref.startsWith("#/")) return { value: {}, name, cycle: false };
    if (seen.includes(ref)) return { value: {}, name, cycle: true };
    let target: Json = root;
    for (const part of ref.slice(2).split("/")) {
      const key = part.replace(/~1/g, "/").replace(/~0/g, "~");
      target = isObj(target) ? target[key] : undefined;
    }
    if (!isObj(target)) return { value: {}, name, cycle: false };
    const inner = resolve(target, [...seen, ref]);
    return { value: inner.value, name: inner.name || name, cycle: inner.cycle };
  };
}

type Resolver = ReturnType<typeof makeResolver>;

/** "string (uuid)", "array of Pet", "integer", "A | B" ... */
function typeLabel(schema: Obj, resolve: Resolver, name = ""): string {
  if (schema.$ref) {
    const r = resolve(schema);
    return r.name || typeLabel(r.value, resolve);
  }
  for (const key of ["oneOf", "anyOf"] as const) {
    const options = schema[key];
    if (Array.isArray(options) && options.length) return options.map((o) => typeLabel(isObj(o) ? o : {}, resolve)).join(" | ");
  }
  if (Array.isArray(schema.allOf) && schema.allOf.length) {
    const names = schema.allOf.map((o) => (isObj(o) && typeof o.$ref === "string" ? refName(o.$ref) : "")).filter(Boolean);
    return names.length ? names.join(" & ") : "object";
  }
  let type = Array.isArray(schema.type) ? schema.type.filter((t) => t !== "null").join(" | ") : str(schema.type);
  if (!type && (isObj(schema.properties) || schema.additionalProperties)) type = "object";
  if (type === "array" && isObj(schema.items)) return `array of ${typeLabel(schema.items, resolve)}`;
  if (Array.isArray(schema.enum) && schema.enum.length) {
    return `${type || "enum"}: ${schema.enum.slice(0, 8).map((v) => JSON.stringify(v)).join(", ")}${schema.enum.length > 8 ? ", …" : ""}`;
  }
  const format = str(schema.format);
  const label = type || name || "any";
  return format ? `${label} (${format})` : label;
}

/** An object's properties, merging allOf parts, after following a ref. */
function properties(schema: Obj, resolve: Resolver, seen: string[]): { props: Obj; required: string[] } {
  const props: Obj = {};
  const required: string[] = [];
  const add = (s: Obj, chain: string[]) => {
    const r = resolve(s, chain);
    if (r.cycle) return;
    const target = r.value;
    if (isObj(target.properties)) Object.assign(props, target.properties);
    if (Array.isArray(target.required)) required.push(...target.required.filter((x): x is string => typeof x === "string"));
    if (Array.isArray(target.allOf)) for (const part of target.allOf) if (isObj(part)) add(part, typeof s.$ref === "string" ? [...chain, s.$ref] : chain);
  };
  add(schema, seen);
  return { props, required };
}

export function describeSchema(schema: Json, root: Obj): ApiSchema | null {
  if (!isObj(schema)) return null;
  const resolve = makeResolver(root);
  const fields: ApiField[] = [];

  const walk = (s: Obj, prefix: string, depth: number, seen: string[]) => {
    if (depth >= MAX_DEPTH || fields.length >= MAX_FIELDS) return;
    const chain = typeof s.$ref === "string" ? [...seen, s.$ref] : seen;
    const target = resolve(s, seen);
    if (target.cycle) return;
    const body = target.value;
    if (str(body.type) === "array" && isObj(body.items)) {
      walk(body.items, prefix ? `${prefix}[]` : "[]", depth, chain);
      return;
    }
    const { props, required } = properties(s, resolve, seen);
    for (const [key, raw] of Object.entries(props)) {
      if (fields.length >= MAX_FIELDS) return;
      const prop = isObj(raw) ? raw : {};
      const resolved = resolve(prop, chain);
      const name = prefix ? `${prefix}.${key}` : key;
      fields.push({
        name,
        type: typeLabel(prop, resolve),
        required: required.includes(key),
        description: str(prop.description) || str(resolved.value.description),
        depth,
      });
      if (resolved.cycle) continue;
      const inner = resolved.value;
      const nested =
        isObj(inner.properties) ||
        Array.isArray(inner.allOf) ||
        (str(inner.type) === "array" && isObj(inner.items) && (isObj(inner.items.properties) || typeof inner.items.$ref === "string"));
      if (nested) walk(prop, name, depth + 1, chain);
    }
  };
  walk(schema, "", 0, []);
  return { type: typeLabel(schema, resolve), fields };
}

function firstContent(content: Json): { contentType: string; schema: Json } {
  if (!isObj(content)) return { contentType: "", schema: undefined };
  const types = Object.keys(content);
  const contentType = types.find((t) => t.includes("json")) ?? types[0] ?? "";
  const media = content[contentType];
  return { contentType, schema: isObj(media) ? media.schema : undefined };
}

function parameter(raw: Json, root: Obj): ApiParameter | null {
  const p = makeResolver(root)(raw).value;
  const name = str(p.name);
  if (!name) return null;
  const schema = isObj(p.schema) ? p.schema : p; // Swagger 2 puts type on the parameter itself
  return {
    name,
    in: str(p.in),
    type: typeLabel(schema, makeResolver(root)),
    required: p.required === true || p.in === "path",
    description: str(p.description),
  };
}

export function buildReference(doc: Json): ApiReference {
  if (!isObj(doc)) throw new Error("The block is not an OpenAPI document (expected a mapping at the top).");
  if (!doc.openapi && !doc.swagger) throw new Error('The block has no "openapi" (or "swagger") version field.');
  if (!isObj(doc.paths)) throw new Error('The document has no "paths".');
  const root = doc;
  const resolve = makeResolver(root);
  const info = isObj(doc.info) ? doc.info : {};

  const servers: string[] = [];
  if (Array.isArray(doc.servers)) for (const s of doc.servers) if (isObj(s) && str(s.url)) servers.push(str(s.url));
  if (!servers.length && str(doc.host)) servers.push(`${Array.isArray(doc.schemes) ? str(doc.schemes[0]) || "https" : "https"}://${str(doc.host)}${str(doc.basePath)}`);

  const tagInfo = new Map<string, string>();
  if (Array.isArray(doc.tags)) for (const t of doc.tags) if (isObj(t) && str(t.name)) tagInfo.set(str(t.name), str(t.description));
  const groups = new Map<string, ApiGroup>();
  for (const name of tagInfo.keys()) groups.set(name, { name, description: tagInfo.get(name) ?? "", operations: [] });
  const used = new Set<string>();

  for (const [path, rawItem] of Object.entries(doc.paths)) {
    const item = resolve(rawItem).value;
    const shared = Array.isArray(item.parameters) ? item.parameters : [];
    for (const method of METHODS) {
      const op = item[method];
      if (!isObj(op)) continue;
      const own = Array.isArray(op.parameters) ? op.parameters : [];
      const byKey = new Map<string, ApiParameter>();
      const swaggerBody = [...shared, ...own].map((p) => resolve(p).value).find((p) => p.in === "body");
      for (const raw of [...shared, ...own]) {
        const p = parameter(raw, root);
        if (p && p.in !== "body" && p.in !== "formData") byKey.set(`${p.in}:${p.name}`, p);
      }

      let body: ApiBody | null = null;
      const requestBody = resolve(op.requestBody).value;
      if (isObj(op.requestBody)) {
        const { contentType, schema } = firstContent(requestBody.content);
        body = { contentType, description: str(requestBody.description), required: requestBody.required === true, schema: describeSchema(schema, root) };
      } else if (swaggerBody) {
        body = { contentType: "application/json", description: str(swaggerBody.description), required: swaggerBody.required === true, schema: describeSchema(swaggerBody.schema, root) };
      }

      const responses: ApiResponse[] = [];
      if (isObj(op.responses)) {
        for (const [status, rawResponse] of Object.entries(op.responses)) {
          const r = resolve(rawResponse).value;
          const { contentType, schema } = isObj(r.content) ? firstContent(r.content) : { contentType: r.schema ? "application/json" : "", schema: r.schema };
          responses.push({ status, description: str(r.description), contentType, schema: describeSchema(schema, root) });
        }
      }

      let id = str(op.operationId) || `${method}-${path}`;
      id = `op-${id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
      while (used.has(id)) id += "-2";
      used.add(id);

      const operation: ApiOperation = {
        id,
        method: method.toUpperCase(),
        path,
        summary: str(op.summary),
        description: str(op.description),
        deprecated: op.deprecated === true,
        parameters: [...byKey.values()],
        body,
        responses,
      };
      const tags = Array.isArray(op.tags) && op.tags.length ? op.tags.map(str).filter(Boolean) : [""];
      const tag = tags[0];
      if (!groups.has(tag)) groups.set(tag, { name: tag, description: tagInfo.get(tag) ?? "", operations: [] });
      groups.get(tag)!.operations.push(operation);
    }
  }

  return {
    title: str(info.title),
    version: str(info.version),
    description: str(info.description),
    servers,
    groups: [...groups.values()].filter((g) => g.operations.length),
  };
}
