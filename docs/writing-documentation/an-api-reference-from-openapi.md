---
order: 18
published: true
title: An API reference from OpenAPI
---

Paste an OpenAPI description into a fenced block marked `openapi` and the
page shows it as an API reference: every endpoint grouped by tag, with its
parameters, request body and responses as tables. Click an endpoint to open
it. YAML and JSON both work, OpenAPI 3.0 and 3.1 as well as Swagger 2.0.

````markdown
```openapi
openapi: 3.1.0
info:
  title: Pet store
  version: "1.0"
paths:
  /pets/{petId}:
    get:
      summary: Get a pet
      ...
```
````

## An example

This is what the block below looks like on the page:

```openapi
openapi: 3.1.0
info:
  title: Pet store
  version: "1.0"
  description: A small example API.
servers:
  - url: https://api.example.com/v1
tags:
  - name: pets
    description: Pets in the store
paths:
  /pets:
    get:
      tags: [pets]
      summary: List pets
      parameters:
        - name: limit
          in: query
          description: How many pets to return, at most 100
          schema: { type: integer, maximum: 100 }
      responses:
        "200":
          description: A page of pets
          content:
            application/json:
              schema:
                type: array
                items: { $ref: "#/components/schemas/Pet" }
    post:
      tags: [pets]
      summary: Add a pet
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/NewPet" }
      responses:
        "201": { description: Created }
        "400": { description: The pet was not valid }
  /pets/{petId}:
    parameters:
      - name: petId
        in: path
        schema: { type: string, format: uuid }
    delete:
      tags: [pets]
      summary: Remove a pet
      responses:
        "204": { description: Removed }
components:
  schemas:
    NewPet:
      type: object
      required: [name]
      properties:
        name: { type: string, description: What the pet is called }
        kind: { type: string, enum: [cat, dog, bird] }
    Pet:
      allOf:
        - { $ref: "#/components/schemas/NewPet" }
        - type: object
          required: [id]
          properties:
            id: { type: string, format: uuid }
```

## What it shows

- The API's title, version, description and servers.
- One group per tag, in the order of the document's `tags` list.
  Endpoints without a tag come last.
- Per endpoint: method, path, summary and description, a **deprecated**
  mark, the parameters (path, query, header, cookie), the request body and
  every response with its status code.
- Schemas as a list of fields, nested objects indented below their parent,
  `*` marking a required one. References within the document (`$ref:
  "#/components/..."`) are followed; a schema that refers back to itself
  stops after its name.

Every endpoint has an anchor of its own, from its `operationId` (or its
method and path), so you can link straight to it: `#op-getpet`.

## What it doesn't do

- References to other files or URLs are shown by name and not fetched. A
  page never loads anything from an address written in the document, so
  paste the whole description into the block.
- Descriptions are shown as plain text, not as Markdown.
- There is no "try it out" button: the page documents the API, it does not
  call it.

A large API is easier to keep up to date in its own page, or split over a
few pages by tag. When the description comes from your code, a
[docs-as-code](/p/docuwaves/pages/docs-as-code) pipeline can write the page
on every release.
