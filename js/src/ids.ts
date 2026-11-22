// Id derivation (decision 0002, "Ids"):
//
//   H(K, label, scope, payload) = epoch || HMAC-SHA-256(K,
//       "kvsig/1" 0x00 label 0x00 u8(len(scope)) scope payload)[0:16]

import { encode } from "./cbor.js";
import { looseMessage, LOOSE_V1, loose as looseCanon, type LooseProfile } from "./loose.js";
import { asCbor, type Canon, type Message } from "./model.js";
import { hmacSha256, sha256 } from "./sha256.js";
import { concatBytes, toHex, utf8 } from "./text.js";

/** The spec label hashed into every id. */
export const SPEC_LABEL = "kvsig/1";
export const KEY_BYTES = 32;

/** A deployment key: 32 secret bytes and the epoch byte that names them. */
export class Key {
  readonly epoch: number;
  readonly #bytes: Uint8Array;

  constructor(epoch: number, bytes: Uint8Array) {
    if (!Number.isInteger(epoch) || epoch < 0 || epoch > 255) {
      throw new RangeError("epoch must be an integer from 0 to 255");
    }
    if (!(bytes instanceof Uint8Array) || bytes.length !== KEY_BYTES) {
      throw new RangeError(`a key is ${KEY_BYTES} bytes`);
    }
    this.epoch = epoch;
    this.#bytes = Uint8Array.from(bytes);
  }

  /**
   * A new random key from Web Crypto `getRandomValues`. Epoch 0 is reserved for
   * test keys. On Node 18, where `globalThis.crypto` is not defined by default,
   * use `new Key(epoch, crypto.randomBytes(32))` from `node:crypto` instead.
   */
  static generate(epoch: number): Key {
    if (epoch === 0) throw new RangeError("epoch 0 is reserved for published test keys");
    const c = (globalThis as { crypto?: { getRandomValues?: (b: Uint8Array) => Uint8Array } }).crypto;
    if (typeof c?.getRandomValues !== "function") {
      throw new Error("Key.generate needs Web Crypto (globalThis.crypto); pass 32 random bytes to new Key() instead");
    }
    const b = new Uint8Array(KEY_BYTES);
    c.getRandomValues(b);
    return new Key(epoch, b);
  }

  /** The secret bytes (a copy). */
  bytes(): Uint8Array {
    return Uint8Array.from(this.#bytes);
  }

  /** @internal */
  mac(...parts: Uint8Array[]): Uint8Array {
    return hmacSha256(this.#bytes, ...parts);
  }

  toString(): string {
    return `Key(epoch=${this.epoch}, <secret>)`;
  }

  toJSON(): string {
    return this.toString();
  }
}

/** The published test key of the spec (epoch 0, bytes 0x00..0x1f). Never protects real data. */
export const TEST_KEY = new Key(0, Uint8Array.from({ length: 32 }, (_, i) => i));

/** The current key and the older keys still accepted during a rotation. */
export class KeyRing {
  readonly current: Key;
  readonly accepted: readonly Key[];

  constructor(current: Key, accepted: readonly Key[] = []) {
    const epochs = new Set([current.epoch]);
    for (const k of accepted) {
      if (epochs.has(k.epoch)) throw new RangeError("every key in a ring needs its own epoch");
      epochs.add(k.epoch);
    }
    this.current = current;
    this.accepted = [...accepted];
  }

  keys(): readonly Key[] {
    return [this.current, ...this.accepted];
  }
}

/**
 * The scope bytes: empty, or SHA-256 of the CBOR map `{"cache_salt": text,
 * "tenant": bytes}` with absent or empty members left out.
 */
export function scopeFrom(opts: { cacheSalt?: string | null; tenant?: Uint8Array | null } = {}): Uint8Array {
  const m: Record<string, string | Uint8Array> = {};
  if (opts.cacheSalt) m.cache_salt = opts.cacheSalt;
  if (opts.tenant && opts.tenant.length > 0) m.tenant = opts.tenant;
  if (Object.keys(m).length === 0) return new Uint8Array(0);
  return sha256(encode(m));
}

type Hasher = (payload: Uint8Array) => Uint8Array;

function hasher(key: Key, label: string, scope: Uint8Array): Hasher {
  if (scope.length > 255) throw new RangeError("scope is at most 255 bytes");
  const prefix = concatBytes([utf8(SPEC_LABEL), Uint8Array.of(0), utf8(label), Uint8Array.of(0, scope.length), scope]);
  const epoch = Uint8Array.of(key.epoch);
  return (payload) => concatBytes([epoch, key.mac(prefix, payload).subarray(0, 16)]);
}

/** Every id of one request, as 34-character lowercase hex strings. */
export interface Ids {
  readonly head: string;
  readonly sys: string;
  readonly tools: string;
  readonly msgs: readonly string[];
  /** Prefix ids; empty for a stateful request. */
  readonly nodes: readonly string[];
  readonly loose_head: string;
  readonly loose_sys: string;
  readonly loose_tools: string;
  readonly loose_msgs: readonly string[];
  readonly loose_nodes: readonly string[];
  /** The conversation id, or null when there is none (or the request is stateful). */
  readonly conv: string | null;
  readonly epoch: number;
  /** The loose profile the loose ids were computed under. */
  readonly profile: string;
}

export interface IdsOptions {
  /** Scope bytes from {@link scopeFrom}; empty by default. */
  scope?: Uint8Array;
  /** The loose profile; `LOOSE_V1` by default. */
  profile?: LooseProfile;
}

function family(
  key: Key,
  scope: Uint8Array,
  prefix: string,
  c: Canon,
): { head: Uint8Array; sys: Uint8Array; tools: Uint8Array; msgs: Uint8Array[]; nodes: Uint8Array[]; msgH: Hasher } {
  const h = (label: string) => hasher(key, prefix + label, scope);
  const head = h("head")(encode(asCbor({ head: c.head, tools: c.tools })));
  const sys = h("sys")(encode(asCbor({ head: c.head })));
  const tools = h("tools")(encode(asCbor({ tools: c.tools })));
  const msgH = h("msg");
  const msgs = c.messages.map((m) => msgH(encode(asCbor(m))));
  const nodes: Uint8Array[] = [];
  if (!c.stateful) {
    const nodeH = h("node");
    let prev = head;
    for (const m of msgs) {
      prev = nodeH(concatBytes([prev, m]));
      nodes.push(prev);
    }
  }
  return { head, sys, tools, msgs, nodes, msgH };
}

/** Every id of `canon` under `key`. */
export function ids(canon: Canon, key: Key, opts: IdsOptions = {}): Ids {
  const scope = opts.scope ?? new Uint8Array(0);
  const profile = opts.profile ?? LOOSE_V1;
  const exact = family(key, scope, "", canon);
  const lc = looseCanon(canon, profile);
  const lp = `${profile.version}:`;
  const lf = family(key, scope, lp, lc);
  let conv: string | null = null;
  if (!canon.stateful) {
    const a = lc.messages.findIndex((m) => m.parts.length > 0);
    if (a >= 0) {
      conv = toHex(hasher(key, lp + "conv", scope)(concatBytes([lf.sys, lf.msgs[a]!])));
    }
  }
  return {
    head: toHex(exact.head),
    sys: toHex(exact.sys),
    tools: toHex(exact.tools),
    msgs: exact.msgs.map(toHex),
    nodes: exact.nodes.map(toHex),
    loose_head: toHex(lf.head),
    loose_sys: toHex(lf.sys),
    loose_tools: toHex(lf.tools),
    loose_msgs: lf.msgs.map(toHex),
    loose_nodes: lf.nodes.map(toHex),
    conv,
    epoch: key.epoch,
    profile: profile.version,
  };
}

/** The ids under every key of a ring, current key first. */
export function idsAllEpochs(canon: Canon, ring: KeyRing, opts: IdsOptions = {}): Ids[] {
  return ring.keys().map((k) => ids(canon, k, opts));
}

export interface MessageIdOptions {
  scope?: Uint8Array;
  /** Give the loose id under this profile; omit for the exact id. */
  profile?: LooseProfile;
}

/**
 * The id of one message: exact, or loose with `profile`. For a reply from
 * {@link canonicalizeReply} it equals the id of the same message in the next request.
 */
export function messageId(m: Message, key: Key, opts: MessageIdOptions = {}): string {
  const scope = opts.scope ?? new Uint8Array(0);
  if (opts.profile === undefined) return toHex(hasher(key, "msg", scope)(encode(asCbor(m))));
  const lm = looseMessage(m, opts.profile);
  return toHex(hasher(key, `${opts.profile.version}:msg`, scope)(encode(asCbor(lm))));
}
