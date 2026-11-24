import { describe, expect, it } from "vitest";
import { buildReference, describeSchema } from "./openapi";

const petstore = {
  openapi: "3.1.0",
  info: { title: "Pet store", version: "1.2", description: "Pets." },
  servers: [{ url: "https://api.example.com/v1" }],
  tags: [{ name: "pets", description: "Everything about pets" }],
  paths: {
    "/pets/{petId}": {
      parameters: [{ name: "petId", in: "path", schema: { type: "string", format: "uuid" } }],
      get: {
        tags: ["pets"],
        operationId: "getPet",
        summary: "Get a pet",
        parameters: [{ $ref: "#/components/parameters/Verbose" }],
        responses: {
          "200": { description: "The pet", content: { "application/json": { schema: { $ref: "#/components/schemas/Pet" } } } },
          "404": { $ref: "#/components/responses/NotFound" },
        },
      },
      delete: { tags: ["pets"], deprecated: true, responses: { "204": { description: "Gone" } } },
    },
    "/health": { get: { responses: { "200": { description: "OK" } } } },
  },
  components: {
    parameters: { Verbose: { name: "verbose", in: "query", schema: { type: "boolean" }, description: "More detail" } },
    responses: { NotFound: { description: "No such pet" } },
    schemas: {
      Pet: {
        type: "object",
        required: ["id"],
        properties: {
          id: { type: "string", format: "uuid" },
          kind: { type: "string", enum: ["cat", "dog"] },
          owner: { $ref: "#/components/schemas/Owner" },
          friends: { type: "array", items: { $ref: "#/components/schemas/Pet" } },
        },
      },
      Owner: { type: "object", properties: { name: { type: "string", description: "Full name" } } },
    },
  },
};

describe("buildReference", () => {
  const api = buildReference(petstore);

  it("reads the header", () => {
    expect(api).toMatchObject({ title: "Pet store", version: "1.2", servers: ["https://api.example.com/v1"] });
  });

  it("groups by tag, untagged last", () => {
    expect(api.groups.map((g) => g.name)).toEqual(["pets", ""]);
    expect(api.groups[0].description).toBe("Everything about pets");
  });

  it("merges path and operation parameters, following refs", () => {
    const get = api.groups[0].operations[0];
    expect(get).toMatchObject({ id: "op-getpet", method: "GET", path: "/pets/{petId}", summary: "Get a pet" });
    expect(get.parameters).toEqual([
      { name: "petId", in: "path", type: "string (uuid)", required: true, description: "" },
      { name: "verbose", in: "query", type: "boolean", required: false, description: "More detail" },
    ]);
  });

  it("describes responses and resolves response refs", () => {
    const get = api.groups[0].operations[0];
    expect(get.responses.map((r) => [r.status, r.description])).toEqual([["200", "The pet"], ["404", "No such pet"]]);
    const fields = get.responses[0].schema!.fields.map((f) => [f.name, f.type, f.required]);
    expect(fields).toEqual([
      ["id", "string (uuid)", true],
      ["kind", 'string: "cat", "dog"', false],
      ["owner", "Owner", false],
      ["owner.name", "string", false],
      ["friends", "array of Pet", false],
    ]);
  });

  it("marks deprecated operations and builds ids without operationId", () => {
    const del = api.groups[0].operations[1];
    expect(del).toMatchObject({ method: "DELETE", deprecated: true, id: "op-delete-pets-petid" });
  });

  it("says what is wrong with a document that is not OpenAPI", () => {
    expect(() => buildReference("hello")).toThrow(/not an OpenAPI document/);
    expect(() => buildReference({ paths: {} })).toThrow(/version field/);
    expect(() => buildReference({ openapi: "3.0.0" })).toThrow(/paths/);
  });

  it("reads Swagger 2.0 bodies and hosts", () => {
    const swagger = buildReference({
      swagger: "2.0",
      host: "api.example.com",
      basePath: "/v2",
      schemes: ["https"],
      paths: { "/pets": { post: { parameters: [{ in: "body", name: "body", required: true, schema: { type: "object", properties: { name: { type: "string" } } } }], responses: { "201": { description: "Created" } } } } },
    });
    expect(swagger.servers).toEqual(["https://api.example.com/v2"]);
    const post = swagger.groups[0].operations[0];
    expect(post.parameters).toEqual([]);
    expect(post.body?.schema?.fields.map((f) => f.name)).toEqual(["name"]);
  });
});

describe("describeSchema", () => {
  it("stops at a self-reference instead of looping", () => {
    const root = { components: { schemas: { Node: { type: "object", properties: { child: { $ref: "#/components/schemas/Node" } } } } } };
    const schema = describeSchema({ $ref: "#/components/schemas/Node" }, root)!;
    expect(schema.type).toBe("Node");
    expect(schema.fields.length).toBeLessThanOrEqual(4);
    expect(schema.fields[0]).toMatchObject({ name: "child", type: "Node" });
  });

  it("does not follow references to other files", () => {
    expect(describeSchema({ $ref: "https://evil.example/schema.json" }, {})).toEqual({ type: "schema.json", fields: [] });
  });

  it("merges allOf parts", () => {
    const root = { components: { schemas: { Base: { type: "object", required: ["id"], properties: { id: { type: "integer" } } } } } };
    const schema = describeSchema({ allOf: [{ $ref: "#/components/schemas/Base" }, { properties: { name: { type: "string" } } }] }, root)!;
    expect(schema.fields.map((f) => [f.name, f.required])).toEqual([["id", true], ["name", false]]);
  });
});
