/**
 * The browser half of signing in with a security key or passkey.
 *
 * The server sends its options as JSON (binary fields base64url-encoded,
 * see py_webauthn's options_to_json) and wants the key's answer back the
 * same way. Browsers that have PublicKeyCredential.parse*OptionsFromJSON and
 * credential.toJSON() do that conversion themselves; the helpers below do it
 * by hand so older Safari and Firefox versions work too.
 */

type Json = Record<string, unknown>;

export function webauthnSupported(): boolean {
  return typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;
}

function fromB64url(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toB64url(buffer: ArrayBuffer | null | undefined): string {
  if (!buffer) return "";
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list)) return undefined;
  return list.map((d: Json) => ({
    type: "public-key",
    id: fromB64url(String(d.id)),
    transports: d.transports as AuthenticatorTransport[] | undefined,
  }));
}

/** Registers a new key. Resolves to what POST /api/auth/mfa/keys takes. */
export async function createCredential(options: Json): Promise<Json> {
  const user = options.user as Json;
  const publicKey: PublicKeyCredentialCreationOptions = {
    ...(options as object),
    challenge: fromB64url(String(options.challenge)),
    user: { ...(user as object), id: fromB64url(String(user.id)) } as PublicKeyCredentialUserEntity,
    excludeCredentials: descriptors(options.excludeCredentials),
  } as PublicKeyCredentialCreationOptions;
  const credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error("cancelled");
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      attestationObject: toB64url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** Signs in with a registered key. Resolves to what the login step takes. */
export async function getAssertion(options: Json): Promise<Json> {
  const publicKey: PublicKeyCredentialRequestOptions = {
    ...(options as object),
    challenge: fromB64url(String(options.challenge)),
    allowCredentials: descriptors(options.allowCredentials),
  } as PublicKeyCredentialRequestOptions;
  const credential = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error("cancelled");
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      authenticatorData: toB64url(response.authenticatorData),
      signature: toB64url(response.signature),
      userHandle: response.userHandle ? toB64url(response.userHandle) : null,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}
