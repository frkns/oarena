import {
  V as m,
  E as y,
  o as Oe,
  U as Ea,
  q as re,
  e as Qe,
  P as qe,
  A as Ra,
  Q as Os,
  O as js,
  d as ge,
  Y as Ua,
  C as Is,
  s as Ka,
  t as Ya,
  M as c,
  R as Xa,
  X as za,
  W as Do,
  L as Lo,
  N as Rn,
  r as Za,
} from "./app-ngkJrQ_K.js";
const Fo = 100,
  gr = [
    {
      tier: "legendary_grandmaster",
      label: "Legendary Grandmaster",
      minRating: 3e3,
      hexColor: "#ef4444",
      lightColor: "#dc2626",
      darkColor: "#ef4444",
      holographic: !0,
    },
    {
      tier: "grandmaster",
      label: "Grandmaster",
      minRating: 2500,
      hexColor: "#DC2626",
      lightColor: "#dc2626",
      darkColor: "#dc2626",
    },
    {
      tier: "master",
      label: "Master",
      minRating: 2300,
      hexColor: "#EC4899",
      lightColor: "#db2777",
      darkColor: "#ec4899",
    },
    {
      tier: "candidate_master",
      label: "Candidate Master",
      minRating: 2100,
      hexColor: "#3B82F6",
      lightColor: "#1d4ed8",
      darkColor: "#2563eb",
    },
    {
      tier: "diamond",
      label: "Diamond",
      minRating: 1900,
      hexColor: "#38BDF8",
      lightColor: "#0ea5e9",
      darkColor: "#38bdf8",
    },
    {
      tier: "emerald",
      label: "Emerald",
      minRating: 1700,
      hexColor: "#10B981",
      lightColor: "#10b981",
      darkColor: "#34d399",
    },
    {
      tier: "gold",
      label: "Gold",
      minRating: 1500,
      hexColor: "#D97706",
      lightColor: "#ca8a04",
      darkColor: "#fbbf24",
    },
    {
      tier: "silver",
      label: "Silver",
      minRating: 1300,
      hexColor: "#CBD5E1",
      lightColor: "#94a3b8",
      darkColor: "#e2e8f0",
    },
    {
      tier: "bronze",
      label: "Bronze",
      minRating: -1 / 0,
      hexColor: "#78350F",
      lightColor: "#6b3410",
      darkColor: "#b45309",
    },
  ],
  Qa = {
    tier: "unranked",
    label: "Unranked",
    minRating: 0,
    hexColor: "#374151",
    lightColor: "#6b7280",
    darkColor: "#4b5563",
  };
function Ja(e, t) {
  return t < Fo ? Qa : (gr.find((n) => e >= n.minRating) ?? gr[gr.length - 1]);
}
const Ho = m.createContext("dark"),
  el = () => m.useContext(Ho);
function gameConstant(
  e,
  t,
  n = globalThis.__OARENA_FCODE_METADATA__?.game_constants,
) {
  const r = n?.[e];
  return typeof r === "number" && Number.isFinite(r) ? r : t;
}
function snapshotGameConstants(t = globalThis.__OARENA_FCODE_METADATA__) {
  const e = t?.game_constants;
  return e && typeof e === "object" ? { ...e } : {};
}
const Ps = 500,
  tl = {
    nested: {
      battlecode: {
        nested: {
          Replay: {
            fields: {
              map: { type: "Map", id: 1 },
              turns: { rule: "repeated", type: "Turn", id: 3 },
              winner: { type: "Team", id: 4, options: { proto3_optional: !0 } },
            },
          },
          Map: {
            fields: {
              width: { type: "int32", id: 1 },
              height: { type: "int32", id: 2 },
              rows: { rule: "repeated", type: "TileRow", id: 3 },
              cores: { rule: "repeated", type: "CorePosition", id: 4 },
            },
          },
          TileRow: {
            fields: { tiles: { rule: "repeated", type: "Environment", id: 1 } },
          },
          Players: {
            fields: {
              a: { type: "Player", id: 1 },
              b: { type: "Player", id: 2 },
            },
          },
          Player: {
            fields: {
              titanium: { type: "int32", id: 1 },
              // Legacy 2.2 fields are retained so archived replays still decode.
              axionite: { type: "int32", id: 2 },
              resourcesCollected: { type: "int32", id: 3 },
              titaniumCollected: { type: "int32", id: 4 },
              axioniteCollected: { type: "int32", id: 5 },
              // FCode 2.3 moved ammunition into the per-player state.
              ammo: { type: "int32", id: 7 },
            },
          },
          Turn: {
            fields: { updates: { rule: "repeated", type: "Update", id: 1 } },
          },
          Update: {
            oneofs: {
              kind: {
                oneof: [
                  "placeEntity",
                  "moveBuilderBot",
                  "removeEntity",
                  "distributeResources",
                  "updateHp",
                  "updatePlayers",
                  "setActionCooldown",
                  "setMoveCooldown",
                  "botOutput",
                  "indicatorLine",
                  "indicatorDot",
                  "builderAttack",
                  "fireTurret",
                  "coreConvertAmmo",
                  "builderHeal",
                  "builderBuild",
                ],
              },
            },
            fields: {
              placeEntity: { type: "PlaceEntity", id: 1 },
              moveBuilderBot: { type: "MoveBuilderBot", id: 2 },
              removeEntity: { type: "RemoveEntity", id: 3 },
              distributeResources: { type: "DistributeResources", id: 4 },
              updateHp: { type: "UpdateHp", id: 5 },
              updatePlayers: { type: "UpdatePlayers", id: 6 },
              setActionCooldown: { type: "SetActionCooldown", id: 7 },
              setMoveCooldown: { type: "SetMoveCooldown", id: 8 },
              botOutput: { type: "BotOutput", id: 9 },
              indicatorLine: { type: "IndicatorLine", id: 10 },
              indicatorDot: { type: "IndicatorDot", id: 11 },
              fireTurret: { type: "FireTurret", id: 12 },
              builderAttack: { type: "BuilderAttack", id: 13 },
              coreConvertAmmo: { type: "CoreConvertAmmo", id: 14 },
              builderHeal: { type: "BuilderHeal", id: 15 },
              builderBuild: { type: "BuilderBuild", id: 16 },
            },
          },
          PlaceEntity: { fields: { entity: { type: "Entity", id: 1 } } },
          MoveBuilderBot: {
            fields: {
              id: { type: "int32", id: 1 },
              to: { type: "Pos", id: 2 },
            },
          },
          RemoveEntity: { fields: { id: { type: "int32", id: 1 } } },
          DistributeResources: {
            fields: {
              moves: { rule: "repeated", type: "ResourceMove", id: 1 },
            },
          },
          ResourceMove: {
            fields: {
              from: { type: "Pos", id: 1 },
              to: { type: "Pos", id: 2 },
              resourceId: {
                type: "int32",
                id: 3,
                options: { proto3_optional: !0 },
              },
            },
          },
          UpdateHp: {
            fields: {
              id: { type: "int32", id: 1 },
              delta: { type: "int32", id: 2 },
            },
          },
          UpdatePlayers: { fields: { players: { type: "Players", id: 1 } } },
          SetActionCooldown: {
            fields: {
              id: { type: "int32", id: 1 },
              value: { type: "int32", id: 2 },
            },
          },
          SetMoveCooldown: {
            fields: {
              id: { type: "int32", id: 1 },
              value: { type: "int32", id: 2 },
            },
          },
          BotOutput: {
            fields: {
              id: { type: "int32", id: 1 },
              stdout: { type: "string", id: 2 },
              execTimeUs: { type: "uint32", id: 3 },
              tled: { type: "bool", id: 4 },
            },
          },
          IndicatorLine: {
            fields: {
              id: { type: "int32", id: 1 },
              posA: { type: "Pos", id: 2 },
              posB: { type: "Pos", id: 3 },
              r: { type: "int32", id: 4 },
              g: { type: "int32", id: 5 },
              b: { type: "int32", id: 6 },
            },
          },
          IndicatorDot: {
            fields: {
              id: { type: "int32", id: 1 },
              pos: { type: "Pos", id: 2 },
              r: { type: "int32", id: 3 },
              g: { type: "int32", id: 4 },
              b: { type: "int32", id: 5 },
            },
          },
          BuilderAttack: {
            fields: {
              id: { type: "int32", id: 1 },
              target: { type: "Pos", id: 2 },
            },
          },
          BuilderHeal: {
            fields: {
              id: { type: "int32", id: 1 },
              target: { type: "Pos", id: 2 },
            },
          },
          BuilderBuild: {
            fields: {
              id: { type: "int32", id: 1 },
              target: { type: "Pos", id: 2 },
            },
          },
          FireTurret: {
            fields: {
              from: { type: "Pos", id: 1 },
              to: { type: "Pos", id: 2 },
            },
          },
          CoreConvertAmmo: {
            fields: {
              team: { type: "Team", id: 1 },
              amount: { type: "int32", id: 2 },
            },
          },
          Pos: {
            fields: {
              x: { type: "int32", id: 1 },
              y: { type: "int32", id: 2 },
            },
          },
          CorePosition: {
            fields: {
              id: { type: "int32", id: 1 },
              team: { type: "Team", id: 2 },
              position: { type: "Pos", id: 3 },
            },
          },
          Entity: {
            oneofs: {
              kind: {
                oneof: [
                  "builderBot",
                  "conveyor",
                  "splitter",
                  "armouredConveyor",
                  "bridge",
                  "harvester",
                  "foundry",
                  "barrier",
                  "core",
                  "gunner",
                  "sentinel",
                  "breach",
                  "launcher",
                ],
              },
            },
            fields: {
              id: { type: "int32", id: 1 },
              team: { type: "Team", id: 2 },
              position: { type: "Pos", id: 3 },
              hp: { type: "int32", id: 4 },
              maxHp: { type: "int32", id: 5 },
              builderBot: { type: "BuilderBot", id: 10 },
              conveyor: { type: "Conveyor", id: 11 },
              splitter: { type: "Splitter", id: 12 },
              armouredConveyor: { type: "ArmouredConveyor", id: 13 },
              bridge: { type: "Bridge", id: 14 },
              harvester: { type: "Harvester", id: 15 },
              foundry: { type: "Foundry", id: 16 },
              barrier: { type: "Barrier", id: 18 },
              core: { type: "Core", id: 20 },
              gunner: { type: "Gunner", id: 21 },
              sentinel: { type: "Sentinel", id: 22 },
              breach: { type: "Breach", id: 23 },
              launcher: { type: "Launcher", id: 24 },
            },
          },
          BuilderBot: {
            fields: {
              actionCooldown: { type: "int32", id: 1 },
              moveCooldown: { type: "int32", id: 2 },
            },
          },
          Conveyor: {
            fields: {
              direction: { type: "Direction", id: 1 },
              stored: { type: "ResourceType", id: 2 },
            },
          },
          Splitter: {
            fields: {
              direction: { type: "Direction", id: 1 },
              stored: { type: "ResourceType", id: 2 },
            },
          },
          ArmouredConveyor: {
            fields: {
              direction: { type: "Direction", id: 1 },
              stored: { type: "ResourceType", id: 2 },
            },
          },
          Bridge: {
            fields: {
              target: { type: "Pos", id: 1 },
              stored: { type: "ResourceType", id: 2 },
            },
          },
          Harvester: {
            fields: {
              cooldown: { type: "int32", id: 1 },
              resourceType: { type: "ResourceType", id: 2 },
            },
          },
          Foundry: { fields: { stored: { type: "ResourceType", id: 2 } } },
          Barrier: { fields: {} },
          Core: { fields: { actionCooldown: { type: "int32", id: 1 } } },
          Gunner: {
            fields: {
              direction: { type: "Direction", id: 1 },
              ammoType: { type: "ResourceType", id: 2 },
              ammoAmount: { type: "int32", id: 3 },
            },
          },
          Sentinel: {
            fields: {
              direction: { type: "Direction", id: 1 },
              ammoType: { type: "ResourceType", id: 2 },
              ammoAmount: { type: "int32", id: 3 },
            },
          },
          Breach: {
            fields: {
              direction: { type: "Direction", id: 1 },
              ammoType: { type: "ResourceType", id: 2 },
              ammoAmount: { type: "int32", id: 3 },
            },
          },
          Launcher: {
            fields: {
              ammoType: { type: "ResourceType", id: 2 },
              ammoAmount: { type: "int32", id: 3 },
            },
          },
          Team: { values: { TEAM_A: 0, TEAM_B: 1 } },
          Direction: {
            values: {
              DIR_CENTRE: 0,
              DIR_NORTH: 1,
              DIR_NORTHEAST: 2,
              DIR_EAST: 3,
              DIR_SOUTHEAST: 4,
              DIR_SOUTH: 5,
              DIR_SOUTHWEST: 6,
              DIR_WEST: 7,
              DIR_NORTHWEST: 8,
            },
          },
          ResourceType: {
            values: {
              RESOURCE_NONE: 0,
              RESOURCE_TITANIUM: 1,
              RESOURCE_RAW_AXIONITE: 2,
              RESOURCE_REFINED_AXIONITE: 3,
            },
          },
          Environment: {
            values: {
              ENV_EMPTY: 0,
              ENV_WALL: 1,
              ENV_ORE_TITANIUM: 2,
              ENV_ORE_AXIONITE: 3,
            },
          },
        },
      },
    },
  };
let xr = null;
function sl() {
  return (
    xr || (xr = Ea.Root.fromJSON(tl).lookupType("battlecode.Replay")),
    xr
  );
}
function Tt(e) {
  const t = e;
  if (!(t == null || t === Oe.None)) return t;
}
function Qn(e) {
  return (
    e === y.Gunner || e === y.Sentinel || e === y.Breach || e === y.Launcher
  );
}
function ol(e, t, n) {
  if (Qn(e.kind)) {
    if (
      ((e.stored = void 0),
      (e.storedId = void 0),
      e.kind === y.Launcher || t === Oe.RawAxionite)
    ) {
      ((e.ammoType = void 0), (e.ammoAmount = 0));
      return;
    }
    ((e.ammoType = t), (e.ammoAmount = gameConstant("STACK_SIZE", 10, n)));
  }
}
function il(e, t) {
  const n =
    e.kind === y.Gunner
      ? gameConstant("GUNNER_AMMO_COST", 2, t)
      : e.kind === y.Sentinel
        ? gameConstant("SENTINEL_AMMO_COST", 10, t)
        : e.kind === y.Breach
          ? 5
          : e.kind === y.Launcher
            ? 0
            : void 0;
  if (n === void 0 || n === 0) return;
  const r = Math.max(0, (e.ammoAmount ?? 0) - n);
  ((e.ammoAmount = r), r === 0 && (e.ammoType = void 0));
}
function al(e) {
  if (e.position == null) return null;
  const t = {
    id: e.id,
    team: e.team,
    position: { x: e.position.x, y: e.position.y },
    hp: e.hp,
    maxHp: e.maxHp,
    kind: y.Barrier,
  };
  if (e.builderBot)
    ((t.kind = y.BuilderBot),
      (t.actionCooldown = e.builderBot.actionCooldown),
      (t.moveCooldown = e.builderBot.moveCooldown));
  else if (e.conveyor)
    ((t.kind = y.Conveyor),
      (t.direction = e.conveyor.direction),
      (t.stored = Tt(e.conveyor.stored)));
  else if (e.splitter)
    ((t.kind = y.Splitter),
      (t.direction = e.splitter.direction),
      (t.stored = Tt(e.splitter.stored)));
  else if (e.armouredConveyor)
    ((t.kind = y.ArmouredConveyor),
      (t.direction = e.armouredConveyor.direction),
      (t.stored = Tt(e.armouredConveyor.stored)));
  else if (e.bridge)
    ((t.kind = y.Bridge),
      (t.bridgeTarget = e.bridge.target
        ? { x: e.bridge.target.x, y: e.bridge.target.y }
        : void 0),
      (t.stored = Tt(e.bridge.stored)));
  else if (e.harvester)
    ((t.kind = y.Harvester),
      (t.harvesterResourceType = e.harvester.resourceType),
      (t.harvesterCooldown = e.harvester.cooldown));
  else if (e.foundry) ((t.kind = y.Foundry), (t.stored = Tt(e.foundry.stored)));
  else if (e.barrier !== void 0 && e.barrier !== null) t.kind = y.Barrier;
  else if (e.core)
    ((t.kind = y.Core), (t.actionCooldown = e.core.actionCooldown));
  else if (e.gunner)
    ((t.kind = y.Gunner),
      (t.direction = e.gunner.direction),
      (t.ammoType = Tt(e.gunner.ammoType)),
      (t.ammoAmount = e.gunner.ammoAmount));
  else if (e.sentinel)
    ((t.kind = y.Sentinel),
      (t.direction = e.sentinel.direction),
      (t.ammoType = Tt(e.sentinel.ammoType)),
      (t.ammoAmount = e.sentinel.ammoAmount));
  else if (e.breach)
    ((t.kind = y.Breach),
      (t.direction = e.breach.direction),
      (t.ammoType = Tt(e.breach.ammoType)),
      (t.ammoAmount = e.breach.ammoAmount));
  else if (e.launcher)
    ((t.kind = y.Launcher),
      (t.ammoType = Tt(e.launcher.ammoType)),
      (t.ammoAmount = e.launcher.ammoAmount));
  else return null;
  return t;
}
function at(e) {
  const t = new Map();
  for (const [n, r] of e.entities)
    t.set(n, {
      ...r,
      position: { ...r.position },
      bridgeTarget: r.bridgeTarget ? { ...r.bridgeTarget } : void 0,
    });
  return {
    turn: e.turn,
    gameConstants: e.gameConstants,
    entities: t,
    players: [{ ...e.players[0] }, { ...e.players[1] }],
    indicatorLines: e.indicatorLines.map((n) => ({
      ...n,
      posA: { ...n.posA },
      posB: { ...n.posB },
    })),
    indicatorDots: e.indicatorDots.map((n) => ({ ...n, pos: { ...n.pos } })),
    builderActions: e.builderActions.map((n) => ({
      ...n,
      pos: { ...n.pos },
      ...(n.targetPos ? { targetPos: { ...n.targetPos } } : {}),
    })),
    tileOutlineEvents: e.tileOutlineEvents.map((n) => ({
      ...n,
      pos: { ...n.pos },
    })),
    turretFires: e.turretFires.map((n) => ({
      turretKind: n.turretKind,
      from: { ...n.from },
      to: { ...n.to },
      team: n.team,
    })),
  };
}
function br(e, t, n, r, s, o) {
  e.builderActions.some(
    (i) => i.botId === t && i.kind === n && i.pos.x === r && i.pos.y === s,
  ) ||
    e.builderActions.push({
      botId: t,
      kind: n,
      pos: { x: r, y: s },
      ...(o ? { targetPos: { ...o } } : {}),
    });
}
function ll(e) {
  return e.kind === y.Core ? 2 : 1;
}
function Bs(e, t, n) {
  const r = ll(n);
  e.tileOutlineEvents.some(
    (o) =>
      o.kind === t &&
      o.tileSpan === r &&
      o.pos.x === n.position.x &&
      o.pos.y === n.position.y,
  ) ||
    e.tileOutlineEvents.push({
      kind: t,
      tileSpan: r,
      pos: { x: n.position.x, y: n.position.y },
    });
}
function cl(e, t, n) {
  for (const r of e.entities.values())
    if (!(r.position.x !== t || r.position.y !== n) && Qn(r.kind))
      return r.kind;
}
function ul(e, t, n) {
  for (const r of e.entities.values())
    if (!(r.position.x !== t || r.position.y !== n) && Qn(r.kind)) return r;
}
function Kt(e, t) {
  for (const r of t)
    if (r.placeEntity) {
      const s = al(r.placeEntity.entity);
      s && (Bs(e, "build", s), e.entities.set(s.id, s));
    } else if (r.moveBuilderBot) {
      const s = e.entities.get(r.moveBuilderBot.id);
      s &&
        (s.position = { x: r.moveBuilderBot.to.x, y: r.moveBuilderBot.to.y });
    } else if (r.removeEntity) {
      const s = e.entities.get(r.removeEntity.id);
      s && (Bs(e, "destroy", s), e.entities.delete(r.removeEntity.id));
    } else if (r.distributeResources) {
      const s = new Map(),
        o = new Map();
      for (const [a, f] of e.entities)
        (s.set(a, f.stored), o.set(a, f.storedId));
      const i = new Map();
      for (const a of e.entities.values())
        if (a.kind !== y.BuilderBot)
          if (a.kind === y.Core)
            for (let f = -1; f <= 1; f++)
              for (let u = -1; u <= 1; u++)
                i.set(`${a.position.x + u},${a.position.y + f}`, a);
          else i.set(`${a.position.x},${a.position.y}`, a);
      for (const a of r.distributeResources.moves || []) {
        const f = a.from,
          u = a.to;
        if (!f || !u) continue;
        const l = i.get(`${f.x},${f.y}`),
          d = i.get(`${u.x},${u.y}`);
        if (!l || !d) continue;
        const p = s.get(l.id),
          g = o.get(l.id);
        let h;
        l.kind === y.Foundry
          ? (h = Oe.RefinedAxionite)
          : p
            ? (h = p)
            : l.kind === y.Harvester &&
              l.harvesterResourceType &&
              (h = l.harvesterResourceType);
        const x = a.resourceId ?? g;
        if (h) {
          if (
            ((a.resolvedResourceType = h),
            l.kind === y.Harvester && (l.harvesterCooldown = 3),
            d.kind !== y.Core)
          )
            if (Qn(d.kind)) ol(d, h, e.gameConstants);
            else if (d.kind === y.Foundry) {
              const v = s.get(d.id) ?? d.stored,
                S = o.get(d.id) ?? d.storedId;
              ((a.resolvedExistingStored = v ?? Oe.None),
                (h === Oe.Titanium && v === Oe.RawAxionite) ||
                (h === Oe.RawAxionite && v === Oe.Titanium)
                  ? ((d.stored = Oe.RefinedAxionite), (d.storedId = S ?? x))
                  : ((d.stored = h), (d.storedId = x)));
            } else ((d.stored = h), (d.storedId = x));
          ((l.stored = void 0), (l.storedId = void 0));
        }
      }
    } else if (r.updateHp) {
      const s = e.entities.get(r.updateHp.id);
      s && (s.hp += r.updateHp.delta);
    } else if (r.updatePlayers) {
      const s = r.updatePlayers.players;
      (s?.a &&
        ((e.players[0].titanium = s.a.titanium),
        (e.players[0].ammo = s.a.ammo ?? 0),
        (e.players[0].axionite = s.a.axionite),
        (e.players[0].resourcesCollected = s.a.resourcesCollected),
        (e.players[0].titaniumCollected = s.a.titaniumCollected ?? 0),
        (e.players[0].axioniteCollected = s.a.axioniteCollected ?? 0)),
        s?.b &&
          ((e.players[1].titanium = s.b.titanium),
          (e.players[1].ammo = s.b.ammo ?? 0),
          (e.players[1].axionite = s.b.axionite),
          (e.players[1].resourcesCollected = s.b.resourcesCollected),
          (e.players[1].titaniumCollected = s.b.titaniumCollected ?? 0),
          (e.players[1].axioniteCollected = s.b.axioniteCollected ?? 0)));
    } else if (r.coreConvertAmmo) {
      // UpdatePlayers is the authoritative post-conversion resource snapshot.
      continue;
    } else if (r.setActionCooldown) {
      const s = e.entities.get(r.setActionCooldown.id);
      s && (s.actionCooldown = r.setActionCooldown.value);
    } else if (r.setMoveCooldown) {
      const s = e.entities.get(r.setMoveCooldown.id);
      s && (s.moveCooldown = r.setMoveCooldown.value);
    } else if (r.botOutput) {
      const s = r.botOutput,
        o = e.entities.get(s.id);
      if (o) {
        const i = s.execTimeUs ?? 0;
        ((o.execTimeUs = i),
          (o.tled = Object.prototype.hasOwnProperty.call(s, "tled")
            ? s.tled
            : i > 5e4),
          s.stdout && (o.stdout = s.stdout));
      }
    } else if (r.indicatorLine) {
      const s = r.indicatorLine;
      e.indicatorLines.push({
        id: s.id,
        posA: { x: s.posA.x, y: s.posA.y },
        posB: { x: s.posB.x, y: s.posB.y },
        r: s.r,
        g: s.g,
        b: s.b,
      });
    } else if (r.indicatorDot) {
      const s = r.indicatorDot;
      e.indicatorDots.push({
        id: s.id,
        pos: { x: s.pos.x, y: s.pos.y },
        r: s.r,
        g: s.g,
        b: s.b,
      });
    } else if (r.builderAttack) {
      const s = r.builderAttack,
        o = e.entities.get(s.id);
      if (o?.kind === y.BuilderBot) {
        const i = s.target ? { x: s.target.x, y: s.target.y } : void 0;
        br(e, o.id, "attack", o.position.x, o.position.y, i);
      }
    } else if (r.builderHeal) {
      const s = r.builderHeal,
        o = e.entities.get(s.id);
      if (o?.kind === y.BuilderBot) {
        const i = s.target ? { x: s.target.x, y: s.target.y } : void 0;
        br(e, o.id, "heal", o.position.x, o.position.y, i);
      }
    } else if (r.builderBuild) {
      const s = r.builderBuild,
        o = e.entities.get(s.id);
      if (o?.kind === y.BuilderBot) {
        const i = s.target ? { x: s.target.x, y: s.target.y } : void 0;
        br(e, o.id, "build", o.position.x, o.position.y, i);
      }
    } else if (r.fireTurret) {
      const s = r.fireTurret,
        o = ul(e, s.from.x, s.from.y);
      (e.turretFires.push({
        turretKind: o?.kind ?? cl(e, s.from.x, s.from.y),
        from: { x: s.from.x, y: s.from.y },
        to: { x: s.to.x, y: s.to.y },
        team: o?.team,
      }),
        o && il(o, e.gameConstants));
    }
}
function vr(e) {
  ((e.indicatorLines = []),
    (e.indicatorDots = []),
    (e.builderActions = []),
    (e.tileOutlineEvents = []),
    (e.turretFires = []));
  for (const t of e.entities.values())
    ((t.tled = !1),
      (t.execTimeUs = void 0),
      (t.stdout = void 0),
      t.actionCooldown !== void 0 && t.actionCooldown > 0 && t.actionCooldown--,
      t.moveCooldown !== void 0 && t.moveCooldown > 0 && t.moveCooldown--,
      t.kind === y.Harvester &&
        t.harvesterCooldown !== void 0 &&
        t.harvesterCooldown > 0 &&
        t.harvesterCooldown--);
}
const Ut = 50;
class dl {
  map;
  winner;
  totalTurns;
  rawTurnUpdates;
  keyframes = new Map();
  cursor = null;
  precomputeHandle = null;
  precomputeFrom = 0;
  disposed = !1;
  timeSeriesCache = new Map();
  constructor(t, n, r, s, o, i = !0) {
    ((this.map = t),
      (this.rawTurnUpdates = n),
      (this.totalTurns = s),
      (this.winner = o),
      this.keyframes.set(0, r),
      i && this.startBackgroundPrecompute());
  }
  getState(t) {
    if (
      ((t = Math.max(0, Math.min(t, this.totalTurns))),
      this.cursor && this.cursor.turn === t)
    )
      return at(this.cursor.state);
    if (this.cursor && this.cursor.turn < t && t - this.cursor.turn <= Ut)
      return (this.advanceCursor(t), at(this.cursor.state));
    const n = this.findNearestKeyframeBefore(t);
    return (
      (this.cursor = { turn: n, state: at(this.keyframes.get(n)) }),
      n < t && this.advanceCursor(t),
      at(this.cursor.state)
    );
  }
  computeTimeSeries(t) {
    const cached = this.timeSeriesCache.get(t);
    if (cached) return cached;
    const n = this.totalTurns + 1,
      r = () => Array.from({ length: n }),
      s = {
        titaniumA: r(),
        titaniumB: r(),
        ammoA: r(),
        ammoB: r(),
        titaniumCollectedA: r(),
        titaniumCollectedB: r(),
        scaleA: r(),
        scaleB: r(),
        harvestersA: r(),
        harvestersB: r(),
      },
      o = at(this.keyframes.get(0));
    this.extractTurnData(s, o, 0, t);
    for (let i = 1; i <= this.totalTurns; i++) {
      ((o.turn = i), vr(o));
      const a = this.rawTurnUpdates[i];
      (a && a.length > 0 && Kt(o, a),
        this.extractTurnData(s, o, i, t),
        i % Ut === 0 && !this.keyframes.has(i) && this.keyframes.set(i, at(o)));
    }
    return (
      (this.precomputeFrom = this.totalTurns),
      this.pauseBackgroundPrecompute(),
      this.timeSeriesCache.set(t, s),
      s
    );
  }
  extractTurnData(t, n, r, s) {
    ((t.titaniumA[r] = n.players[0].titanium),
      (t.titaniumB[r] = n.players[1].titanium),
      (t.ammoA[r] = n.players[0].ammo ?? 0),
      (t.ammoB[r] = n.players[1].ammo ?? 0),
      (t.titaniumCollectedA[r] = n.players[0].titaniumCollected),
      (t.titaniumCollectedB[r] = n.players[1].titaniumCollected));
    let o = 100,
      i = 100,
      a = 0,
      f = 0;
    for (const u of n.entities.values()) {
      const l = s[u.kind] ?? 0;
      (u.team === re.A ? (o += l) : (i += l),
        u.kind === y.Harvester && (u.team === re.A ? a++ : f++));
    }
    ((t.scaleA[r] = o),
      (t.scaleB[r] = i),
      (t.harvestersA[r] = a),
      (t.harvestersB[r] = f));
  }
  advanceCursor(t) {
    if (this.cursor) {
      for (let n = this.cursor.turn + 1; n <= t; n++) {
        ((this.cursor.state.turn = n), vr(this.cursor.state));
        const r = this.rawTurnUpdates[n];
        (r && r.length > 0 && Kt(this.cursor.state, r),
          n % Ut === 0 &&
            !this.keyframes.has(n) &&
            this.keyframes.set(n, at(this.cursor.state)));
      }
      this.cursor.turn = t;
    }
  }
  findNearestKeyframeBefore(t) {
    let n = Math.floor(t / Ut) * Ut;
    for (; n >= 0; ) {
      if (this.keyframes.has(n)) return n;
      n -= Ut;
    }
    return 0;
  }
  startBackgroundPrecompute() {
    this.disposed ||
      this.precomputeHandle !== null ||
      this.precomputeFrom >= this.totalTurns ||
      this.totalTurns <= 0 ||
      this.schedulePrecomputeChunk();
  }
  schedulePrecomputeChunk() {
    if (this.disposed) return;
    typeof requestIdleCallback < "u"
      ? (this.precomputeHandle = requestIdleCallback(
          (t) => this.precomputeChunk(t),
          { timeout: 2e3 },
        ))
      : (this.precomputeHandle = setTimeout(() => this.precomputeChunk(), 16));
  }
  precomputeChunk(t) {
    if (this.disposed) return;
    this.precomputeHandle = null;
    const n = t ? () => t.timeRemaining() > 5 : () => !0;
    for (; this.precomputeFrom < this.totalTurns && n(); ) {
      const r = Math.min(this.precomputeFrom + Ut, this.totalTurns);
      if (!this.keyframes.has(r)) {
        const s = this.keyframes.get(this.precomputeFrom);
        if (!s) break;
        const o = at(s);
        for (let i = this.precomputeFrom + 1; i <= r; i++) {
          ((o.turn = i), vr(o));
          const a = this.rawTurnUpdates[i];
          a && a.length > 0 && Kt(o, a);
        }
        this.keyframes.set(r, o);
      }
      this.precomputeFrom = r;
    }
    !this.disposed &&
      this.precomputeFrom < this.totalTurns &&
      this.schedulePrecomputeChunk();
  }
  pauseBackgroundPrecompute() {
    if (this.precomputeHandle === null) return;
    typeof cancelIdleCallback < "u"
      ? cancelIdleCallback(this.precomputeHandle)
      : clearTimeout(this.precomputeHandle);
    this.precomputeHandle = null;
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = !0;
    this.pauseBackgroundPrecompute();
    this.timeSeriesCache.clear();
  }
}
function fl(e, t = !0, metadata = globalThis.__OARENA_FCODE_METADATA__) {
  const n = sl().decode(new Uint8Array(e)),
    r = n.map,
    s = r.width,
    o = r.height,
    i = [];
  for (let p = 0; p < o; p++) {
    const g = [],
      h = r.rows[p];
    for (let x = 0; x < s; x++) g.push(h?.tiles[x] ?? 0);
    i.push(g);
  }
  const a = { width: s, height: o, environment: i },
    replayGameConstants = snapshotGameConstants(metadata),
    fcodeStartingTitanium = gameConstant(
      "STARTING_TITANIUM",
      Ps,
      replayGameConstants,
    ),
    fcodeCoreMaxHp = gameConstant("CORE_MAX_HP", 500, replayGameConstants),
    f = {
      turn: 0,
      gameConstants: replayGameConstants,
      entities: new Map(),
      players: [
        {
          titanium: fcodeStartingTitanium,
          ammo: 0,
          axionite: 0,
          resourcesCollected: 0,
          titaniumCollected: 0,
          axioniteCollected: 0,
        },
        {
          titanium: fcodeStartingTitanium,
          ammo: 0,
          axionite: 0,
          resourcesCollected: 0,
          titaniumCollected: 0,
          axioniteCollected: 0,
        },
      ],
      indicatorLines: [],
      indicatorDots: [],
      builderActions: [],
      tileOutlineEvents: [],
      turretFires: [],
    };
  for (const p of r.cores || []) {
    const g = {
      id: p.id,
      team: p.team,
      position: { x: p.position.x, y: p.position.y },
      hp: fcodeCoreMaxHp,
      maxHp: fcodeCoreMaxHp,
      kind: y.Core,
      actionCooldown: 0,
    };
    f.entities.set(p.id, g);
  }
  const u = [[]];
  for (const p of n.turns || []) u.push(p.updates || []);
  const l = u.length - 1,
    d = n.winner !== void 0 && n.winner !== null ? n.winner : null;
  return new dl(a, u, at(f), l, d, t);
}
const Z = 128;
const ml = `${Date.now()}`;
function gl() {
  if (typeof window > "u") return "";
  const e = window.location.hostname;
  return e === "localhost" || e === "127.0.0.1" || e.startsWith("staging.")
    ? `?v=${ml}`
    : "";
}
(Qe.Empty + "", Qe.Wall + "", Qe.OreTitanium + "", Qe.OreAxionite + "");
(re.A + "", re.B + "");
const kn = {
    [Oe.Titanium]: 5952767,
    [Oe.RawAxionite]: 13788927,
    [Oe.RefinedAxionite]: 16733695,
  },
  xl = {
    [Oe.Titanium]: "titanium",
    [Oe.RawAxionite]: "axionite_raw",
    [Oe.RefinedAxionite]: "axionite_processed",
  },
  _o = new Set([y.Gunner, y.Sentinel]),
  vl = Z * 1.5;
function visionRadiusForKind(e) {
  switch (e) {
    case y.BuilderBot:
      return gameConstant("BUILDER_BOT_VISION_RADIUS_SQ", 20);
    case y.Core:
      return gameConstant("CORE_VISION_RADIUS_SQ", 36);
    case y.Gunner:
      return gameConstant("GUNNER_VISION_RADIUS_SQ", 13);
    case y.Sentinel:
      return gameConstant("SENTINEL_VISION_RADIUS_SQ", 32);
    case y.Launcher:
      return gameConstant("LAUNCHER_VISION_RADIUS_SQ", 26);
    default:
      return void 0;
  }
}
function actionRadiusForKind(e) {
  if (e === y.BuilderBot) return 1;
  if (e === y.Core) return gameConstant("CORE_ACTION_RADIUS_SQ", 8);
  if (e === y.Launcher) return 2;
  return void 0;
}
function yl(e) {
  switch (e) {
    case ge.North:
      return [0, -1];
    case ge.Northeast:
      return [1, -1];
    case ge.East:
      return [1, 0];
    case ge.Southeast:
      return [1, 1];
    case ge.South:
      return [0, 1];
    case ge.Southwest:
      return [-1, 1];
    case ge.West:
      return [-1, 0];
    case ge.Northwest:
      return [-1, -1];
    default:
      return [0, 0];
  }
}
function Sl(e, t, n) {
  if (!_o.has(e.kind)) return null;
  const r = e.direction ?? ge.Centre,
    [s, o] = yl(r),
    i = e.position.x,
    a = e.position.y,
    f = new Set(),
    u = (l, d) => l >= 0 && d >= 0 && l < t && d < n;
  switch (e.kind) {
    case y.Gunner: {
      const l = visionRadiusForKind(y.Gunner);
      let d = i + s,
        p = a + o;
      for (; u(d, p); ) {
        const g = d - i,
          h = p - a;
        if (g * g + h * h > l) break;
        (f.add(`${d},${p}`), (d += s), (p += o));
      }
      break;
    }
    case y.Sentinel: {
      const l = visionRadiusForKind(y.Sentinel);
      let d = 1;
      for (; d * d * (s * s + o * o) <= l; ) {
        const p = i + d * s,
          g = a + d * o;
        if (u(p, g)) {
          const h = p - i,
            x = g - a;
          h * h + x * x <= l && f.add(`${p},${g}`);
        }
        d++;
      }
      break;
    }
  }
  return f.size > 0 ? f : null;
}
class fn extends qe.Scene {
  replay = null;
  currentTurn = 0;
  botStepMode = !1;
  currentSubStep = 0;
  subStepCache = new Map();
  subStepBotIds = new Map();
  mapLayer;
  entityLayer;
  uiLayer;
  gridGraphics;
  indicatorGraphics;
  turretFireGraphics;
  builderActionGraphics;
  tileOutlineGraphics;
  entitySprites = new Map();
  entityObjects = new Map();
  resourceObjects = new Map();
  prevPositions = new Map();
  prevStored = new Map();
  botFacings = new Map();
  prevBotTiles = new Map();
  shouldAnimate = !1;
  animationDuration = 150;
  swapTeams = !1;
  dragStart = null;
  pointerDownWorld = null;
  static CLICK_THRESHOLD = 8;
  keys;
  static PAN_SPEED = 600;
  static ZOOM_SPEED = 2;
  hoveredTile = null;
  selectedTile = null;
  selectedEntityId = null;
  highlightGraphics;
  rangeGraphics;
  showAllIndicators = !0;
  lastGridHash = -1;
  theme = "dark";
  indicatorsDrawn = !1;
  turretFiresDrawn = !1;
  builderActionsDrawn = !1;
  tileOutlineEventsDrawn = !1;
  onTurnChange;
  onStateChange;
  onHoverChange;
  onSelectChange;
  onSubStepChange;
  onBotStepModeChange;
  constructor() {
    super({ key: "GameScene" });
  }
  preload() {
    const obsoleteAsset =
      /^(?:axionite|armoured_conveyor|bridge|foundry|road|breach)/;
    for (const n of Ra)
      obsoleteAsset.test(n.key) || this.load.image(n.key, n.file);
  }
  create() {
    ((this.mapLayer = this.add.container(0, 0)),
      (this.gridGraphics = this.add.graphics()),
      (this.entityLayer = this.add.container(0, 0)),
      (this.indicatorGraphics = this.add.graphics()),
      (this.turretFireGraphics = this.add.graphics()),
      (this.builderActionGraphics = this.add.graphics()),
      (this.tileOutlineGraphics = this.add.graphics()),
      (this.rangeGraphics = this.add.graphics()),
      (this.highlightGraphics = this.add.graphics()),
      (this.uiLayer = this.add.container(0, 0)),
      this.input.on("pointerdown", (t) => {
        t.leftButtonDown() &&
          ((this.dragStart = { x: t.worldX, y: t.worldY }),
          (this.pointerDownWorld = { x: t.x, y: t.y }));
      }),
      this.input.on("pointermove", (t) => {
        if (this.dragStart && t.leftButtonDown()) {
          const n = this.dragStart.x - t.worldX,
            r = this.dragStart.y - t.worldY;
          ((this.cameras.main.scrollX += n), (this.cameras.main.scrollY += r));
        }
        this.updateHover(t);
      }),
      this.input.on("pointerup", (t) => {
        if (this.pointerDownWorld) {
          const n = this.pointerDownWorld.x - t.x,
            r = this.pointerDownWorld.y - t.y;
          Math.sqrt(n * n + r * r) < fn.CLICK_THRESHOLD &&
            this.handleTileClick(t);
        }
        ((this.dragStart = null), (this.pointerDownWorld = null));
      }),
      this.input.on("wheel", (t, n, r, s) => {
        const o = this.cameras.main,
          i = qe.Math.Clamp(o.zoom * (s > 0 ? 0.9 : 1.1), 0.1, 4);
        o.setZoom(i);
      }),
      this.input.keyboard &&
        (this.keys = {
          w: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.W, !1),
          a: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.A, !1),
          s: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.S, !1),
          d: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.D, !1),
          q: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.Q, !1),
          e: this.input.keyboard.addKey(qe.Input.Keyboard.KeyCodes.E, !1),
        }),
      this.replay &&
        (this.renderMap(), this.renderTurn(), this.centerCamera()));
  }
  update(t, n) {
    if (!this.keys) return;
    const r = this.cameras.main,
      s = (fn.PAN_SPEED * n) / (1e3 * r.zoom);
    if (
      (this.keys.a.isDown && (r.scrollX -= s),
      this.keys.d.isDown && (r.scrollX += s),
      this.keys.w.isDown && (r.scrollY -= s),
      this.keys.s.isDown && (r.scrollY += s),
      this.keys.q.isDown || this.keys.e.isDown)
    ) {
      const o = Math.pow(fn.ZOOM_SPEED, n / 1e3),
        i = this.keys.e.isDown ? r.zoom * o : r.zoom / o;
      r.setZoom(qe.Math.Clamp(i, 0.1, 4));
    }
  }
  isCreated() {
    return !!this.mapLayer;
  }
  setSwapTeams(t) {
    this.swapTeams = t;
  }
  projection = Os("square");
  ground = js("square");
  setTheme(t) {
    ((this.theme = t),
      this.cameras.main.setBackgroundColor(t === "light" ? Go : $o),
      this.mapLayer && this.renderMap());
  }
  clearSelection() {
    ((this.selectedTile = null),
      (this.selectedEntityId = null),
      this.onSelectChange?.(null));
  }
  displayTeam(t) {
    return this.swapTeams ? (t === re.A ? re.B : re.A) : t;
  }
  loadReplay(t) {
    (this.tweens.killAll(),
      (this.replay = t),
      (this.currentTurn = 0),
      (this.currentSubStep = 0),
      (this.botStepMode = !1),
      (this.shouldAnimate = !1),
      this.subStepCache.clear(),
      this.subStepBotIds.clear(),
      this.prevPositions.clear(),
      this.prevStored.clear(),
      this.botFacings.clear(),
      this.prevBotTiles.clear(),
      (this.hoveredTile = null),
      (this.selectedTile = null),
      (this.selectedEntityId = null),
      this.indicatorGraphics?.clear(),
      this.turretFireGraphics?.clear(),
      this.builderActionGraphics?.clear(),
      this.tileOutlineGraphics?.clear(),
      this.rangeGraphics?.clear(),
      this.highlightGraphics?.clear(),
      (this.indicatorsDrawn = !1),
      (this.turretFiresDrawn = !1),
      (this.builderActionsDrawn = !1),
      (this.tileOutlineEventsDrawn = !1),
      (this.lastGridHash = -1),
      this.onHoverChange?.(null),
      this.onSelectChange?.(null),
      this.onBotStepModeChange?.(!1),
      this.onSubStepChange?.(0, 0),
      this.mapLayer &&
        (this.renderMap(), this.renderTurn(), this.centerCamera()));
  }
  setTurn(t) {
    this.replay &&
      ((this.currentTurn = qe.Math.Clamp(t, 0, this.replay.totalTurns)),
      (this.shouldAnimate = !1),
      this.botStepMode && (this.currentSubStep = this.getMaxSubSteps()),
      this.renderTurn());
  }
  nextTurn(t = !1) {
    if (this.replay) {
      if (this.botStepMode) {
        this.nextSubStep(t);
        return;
      }
      this.currentTurn < this.replay.totalTurns &&
        (this.snapshotPositions(),
        this.currentTurn++,
        (this.shouldAnimate = t),
        this.renderTurn());
    }
  }
  advanceTurns(t) {
    if (!this.replay || t <= 0) return 0;
    if (this.botStepMode) {
      let r = 0;
      for (let s = 0; s < t; s++) {
        const o = this.currentSubStep,
          i = this.currentTurn,
          a = this.getMaxSubSteps();
        if (this.currentSubStep < a) this.currentSubStep++;
        else if (this.currentTurn < this.replay.totalTurns)
          (this.currentTurn++, (this.currentSubStep = 1));
        else break;
        if (this.currentSubStep === o && this.currentTurn === i) break;
        r++;
      }
      return (r > 0 && ((this.shouldAnimate = !1), this.renderTurn()), r);
    }
    const n = Math.min(t, this.replay.totalTurns - this.currentTurn);
    return (
      (this.currentTurn += n),
      n > 0 && ((this.shouldAnimate = !1), this.renderTurn()),
      n
    );
  }
  prevTurn() {
    if (this.replay) {
      if (this.botStepMode) {
        this.prevSubStep();
        return;
      }
      this.currentTurn > 0 &&
        (this.currentTurn--, (this.shouldAnimate = !1), this.renderTurn());
    }
  }
  getTurn() {
    return this.currentTurn;
  }
  getMaxTurn() {
    return this.replay ? this.replay.totalTurns : 0;
  }
  setOnTurnChange(t) {
    this.onTurnChange = t;
  }
  setOnStateChange(t) {
    this.onStateChange = t;
  }
  setAnimationDuration(t) {
    this.animationDuration = t;
  }
  setOnHoverChange(t) {
    this.onHoverChange = t;
  }
  setOnSelectChange(t) {
    this.onSelectChange = t;
  }
  setOnSubStepChange(t) {
    this.onSubStepChange = t;
  }
  setOnBotStepModeChange(t) {
    this.onBotStepModeChange = t;
  }
  setBotStepMode(t) {
    (t && !this.botStepMode
      ? this.replay &&
        this.currentTurn < this.replay.totalTurns &&
        this.currentTurn++
      : !t && this.botStepMode && this.currentTurn > 0 && this.currentTurn--,
      (this.botStepMode = t),
      (this.currentSubStep = 1),
      this.onBotStepModeChange?.(t),
      this.renderTurn());
  }
  getBotStepMode() {
    return this.botStepMode;
  }
  setShowAllIndicators(t) {
    ((this.showAllIndicators = t), this.redrawIndicators());
  }
  adjustZoom(t) {
    const n = this.cameras.main;
    n.setZoom(qe.Math.Clamp(n.zoom * t, 0.1, 4));
  }
  resetZoom() {
    this.centerCamera();
  }
  redrawIndicators() {
    const t = this.getCurrentState();
    t && this.renderIndicators(t.indicatorLines, t.indicatorDots);
  }
  getSubStep() {
    return this.currentSubStep;
  }
  getMaxSubSteps() {
    return this.replay ? this.getSubSteps(this.currentTurn).length : 0;
  }
  getSubSteps(t) {
    const n = this.subStepCache.get(t);
    if (n) return n;
    if (!this.replay) return [];
    if (t === 0) {
      const d = [this.replay.getState(0)];
      return (this.subStepCache.set(0, d), this.subStepBotIds.set(0, [-1]), d);
    }
    const r = this.replay.getState(t - 1);
    if (!r) return [];
    const s = this.replay.rawTurnUpdates[t];
    if (!s || s.length === 0) {
      const d = [this.replay.getState(t)];
      return (this.subStepCache.set(t, d), this.subStepBotIds.set(t, [-1]), d);
    }
    const o = at(r);
    ((o.turn = t),
      (o.indicatorLines = []),
      (o.indicatorDots = []),
      (o.builderActions = []),
      (o.tileOutlineEvents = []),
      (o.turretFires = []));
    for (const d of o.entities.values())
      ((d.tled = !1), (d.execTimeUs = void 0), (d.stdout = void 0));
    const i = s,
      a = [],
      f = [];
    let u = 0;
    const l = i.findIndex((d) => d.distributeResources);
    for (let d = 0; d < i.length; d++)
      i[d].botOutput &&
        (Kt(o, i.slice(u, d + 1)),
        a.push(at(o)),
        f.push(i[d].botOutput.id ?? -1),
        (u = d + 1));
    return (
      l !== -1 &&
        (u <= l && (Kt(o, i.slice(u, l)), (u = l)),
        Kt(o, [i[l]]),
        (u = l + 1),
        a.push(at(o)),
        f.push(-2)),
      u < i.length && Kt(o, i.slice(u)),
      a.length === 0 && (a.push(this.replay.getState(t)), f.push(-1)),
      this.subStepCache.set(t, a),
      this.subStepBotIds.set(t, f),
      a
    );
  }
  nextSubStep(t = !1) {
    if (!this.replay || !this.botStepMode) return;
    const n = this.getMaxSubSteps();
    this.currentSubStep < n
      ? (this.snapshotPositions(),
        this.currentSubStep++,
        (this.shouldAnimate = t),
        this.renderTurn())
      : this.currentTurn < this.replay.totalTurns &&
        (this.snapshotPositions(),
        this.currentTurn++,
        (this.currentSubStep = 1),
        (this.shouldAnimate = t),
        this.renderTurn());
  }
  prevSubStep() {
    !this.replay ||
      !this.botStepMode ||
      (this.currentSubStep > 1
        ? (this.currentSubStep--, (this.shouldAnimate = !1), this.renderTurn())
        : this.currentTurn > 0 &&
          (this.currentTurn--,
          (this.currentSubStep = this.getMaxSubSteps()),
          (this.shouldAnimate = !1),
          this.renderTurn()));
  }
  getCurrentState() {
    if (!this.replay) return null;
    if (this.botStepMode && this.currentSubStep > 0) {
      const t = this.getSubSteps(this.currentTurn);
      if (this.currentSubStep <= t.length) return t[this.currentSubStep - 1];
    }
    return this.replay.getState(this.currentTurn) ?? null;
  }
  getCurrentSubStepBotId() {
    if (!this.botStepMode || this.currentSubStep <= 0) return -1;
    const t = this.subStepBotIds.get(this.currentTurn);
    if (!t) return -1;
    const n = this.currentSubStep - 1;
    return n < t.length ? t[n] : -1;
  }
  worldToTile(t, n) {
    return this.replay
      ? this.projection.toTile(
          t,
          n,
          this.replay.map.width,
          this.replay.map.height,
        )
      : null;
  }
  buildTileInfo(t, n) {
    if (!this.replay) return null;
    const r = this.getCurrentState();
    if (!r) return null;
    const s = this.replay.map.environment[n]?.[t] ?? Qe.Empty,
      o = [];
    for (const i of r.entities.values())
      if (i.kind === y.Core) {
        const a = t - i.position.x,
          f = n - i.position.y;
        a >= 0 && a <= 1 && f >= 0 && f <= 1 && o.push(i);
      } else i.position.x === t && i.position.y === n && o.push(i);
    return (
      o.sort((i, a) =>
        i.kind === y.BuilderBot && a.kind !== y.BuilderBot
          ? -1
          : i.kind !== y.BuilderBot && a.kind === y.BuilderBot
            ? 1
            : 0,
      ),
      { pos: { x: t, y: n }, environment: s, entities: o }
    );
  }
  updateHover(t) {
    const n = this.worldToTile(t.worldX, t.worldY),
      r = this.hoveredTile;
    (n?.x === r?.x && n?.y === r?.y) ||
      ((this.hoveredTile = n),
      n
        ? this.onHoverChange?.(this.buildTileInfo(n.x, n.y))
        : this.onHoverChange?.(null),
      this.drawHighlights(),
      this.showAllIndicators || this.redrawIndicators());
  }
  handleTileClick(t) {
    const n = this.worldToTile(t.worldX, t.worldY);
    if (!n) {
      ((this.selectedTile = null),
        (this.selectedEntityId = null),
        this.onSelectChange?.(null),
        this.drawHighlights());
      return;
    }
    if (
      this.selectedTile &&
      this.selectedEntityId === null &&
      this.selectedTile.x === n.x &&
      this.selectedTile.y === n.y
    ) {
      ((this.selectedTile = null),
        (this.selectedEntityId = null),
        this.onSelectChange?.(null),
        this.drawHighlights());
      return;
    }
    if (
      this.selectedEntityId !== null &&
      this.buildTileInfo(n.x, n.y)?.entities.some(
        (a) => a.id === this.selectedEntityId,
      )
    ) {
      ((this.selectedTile = null),
        (this.selectedEntityId = null),
        this.onSelectChange?.(null),
        this.drawHighlights());
      return;
    }
    const r = this.buildTileInfo(n.x, n.y);
    if (!r) return;
    const s = r.entities.find((o) => o.kind === y.BuilderBot);
    (s
      ? ((this.selectedEntityId = s.id),
        (this.selectedTile = { x: n.x, y: n.y }))
      : ((this.selectedEntityId = null),
        (this.selectedTile = { x: n.x, y: n.y })),
      this.emitSelectInfo(),
      this.drawHighlights());
  }
  emitSelectInfo() {
    if (!this.replay) {
      this.onSelectChange?.(null);
      return;
    }
    if (this.selectedEntityId !== null) {
      const t = this.getCurrentState();
      if (!t) {
        this.onSelectChange?.(null);
        return;
      }
      const n = t.entities.get(this.selectedEntityId);
      if (!n) {
        ((this.selectedEntityId = null),
          (this.selectedTile = null),
          this.onSelectChange?.(null));
        return;
      }
      ((this.selectedTile = { x: n.position.x, y: n.position.y }),
        this.onSelectChange?.(this.buildTileInfo(n.position.x, n.position.y)));
    } else
      this.selectedTile
        ? this.onSelectChange?.(
            this.buildTileInfo(this.selectedTile.x, this.selectedTile.y),
          )
        : this.onSelectChange?.(null);
  }
  roundedLine(t, n, r, s, o, i, a, f) {
    t.lineBetween(n, r, s, o);
    const u = i / 2;
    (t.fillStyle(a, 1), t.fillCircle(n, r, u), t.fillCircle(s, o, u));
  }
  drawHighlights() {
    (this.highlightGraphics.clear(), this.rangeGraphics.clear());
    const t = this.getRangeEntity();
    if ((t && this.drawRangeOverlay(t), this.selectedTile)) {
      const n = this.findCoreCovering(this.selectedTile.x, this.selectedTile.y);
      n
        ? this.drawTileHighlight(n.position.x + 0.5, n.position.y + 0.5, 8, 2)
        : this.drawTileHighlight(this.selectedTile.x, this.selectedTile.y, 8);
    }
    if (
      this.hoveredTile &&
      !(
        this.selectedTile &&
        this.hoveredTile.x === this.selectedTile.x &&
        this.hoveredTile.y === this.selectedTile.y
      )
    ) {
      const n = this.findCoreCovering(this.hoveredTile.x, this.hoveredTile.y);
      n
        ? this.drawTileHighlight(n.position.x + 0.5, n.position.y + 0.5, 4, 2)
        : this.drawTileHighlight(this.hoveredTile.x, this.hoveredTile.y, 4);
    }
  }
  findCoreCovering(t, n) {
    const r = this.getCurrentState();
    if (!r) return null;
    for (const s of r.entities.values()) {
      if (s.kind !== y.Core) continue;
      const o = t - s.position.x,
        i = n - s.position.y;
      if (o >= 0 && o <= 1 && i >= 0 && i <= 1) return s;
    }
    return null;
  }
  drawTileHighlight(t, n, r, s = 1) {
    const o = this.highlightGraphics;
    const i = t * Z,
      a = n * Z,
      f = r >= 8 ? 4 : 2;
    (o.lineStyle(r, 16777215, 1),
      this.roundedLine(o, i + f, a + f, i + Z - f, a + f, r, 16777215, 1),
      this.roundedLine(
        o,
        i + Z - f,
        a + f,
        i + Z - f,
        a + Z - f,
        r,
        16777215,
        1,
      ),
      this.roundedLine(
        o,
        i + Z - f,
        a + Z - f,
        i + f,
        a + Z - f,
        r,
        16777215,
        1,
      ),
      this.roundedLine(o, i + f, a + Z - f, i + f, a + f, r, 16777215, 1));
  }
  getRangeEntity() {
    const t = this.getCurrentState();
    if (!t) return null;
    if (this.selectedEntityId !== null) {
      const n = t.entities.get(this.selectedEntityId);
      if (n && visionRadiusForKind(n.kind) !== void 0) return n;
    }
    if (this.selectedTile) {
      const n = this.findUnitOnTile(
        t,
        this.selectedTile.x,
        this.selectedTile.y,
      );
      if (n) return n;
    }
    if (this.hoveredTile) {
      const n = this.findUnitOnTile(t, this.hoveredTile.x, this.hoveredTile.y);
      if (n) return n;
    }
    return null;
  }
  findUnitOnTile(t, n, r) {
    for (const s of t.entities.values())
      if (visionRadiusForKind(s.kind) !== void 0) {
        if (s.kind === y.Core) {
          const o = n - s.position.x,
            i = r - s.position.y;
          if (o >= 0 && o <= 1 && i >= 0 && i <= 1) return s;
        } else if (s.position.x === n && s.position.y === r) return s;
      }
    return null;
  }
  drawRangeOverlay(t) {
    if (!this.replay) return;
    const { width: n, height: r } = this.replay.map,
      s = t.position.x,
      o = t.position.y,
      i = visionRadiusForKind(t.kind);
    if (i === void 0) return;
    const a =
        t.kind === y.Core
          ? [
              [0, 0],
              [1, 0],
              [0, 1],
              [1, 1],
            ]
          : [[0, 0]],
      f = (S, b) => {
        let C = 1 / 0;
        for (const [w, R] of a) {
          const E = (S - w) * (S - w) + (b - R) * (b - R);
          E < C && (C = E);
        }
        return C;
      },
      u = t.kind === y.Core ? 1 : 0,
      l = (S, b) => {
        const C = s + S,
          w = o + b;
        return f(S, b) <= i && C >= 0 && w >= 0 && C < n && w < r;
      },
      d = Math.ceil(Math.sqrt(i)),
      x = (S, b, C, w, R) => {
        this.rangeGraphics.lineStyle(R, C, w);
        for (let E = -b; E <= b; E++)
          for (let T = -b; T <= b; T++) {
            if (!S(T, E)) continue;
            const O = (s + T) * Z,
              A = (o + E) * Z;
            (S(T, E - 1) ||
              this.roundedLine(this.rangeGraphics, O, A, O + Z, A, R, C, w),
              S(T, E + 1) ||
                this.roundedLine(
                  this.rangeGraphics,
                  O,
                  A + Z,
                  O + Z,
                  A + Z,
                  R,
                  C,
                  w,
                ),
              S(T - 1, E) ||
                this.roundedLine(this.rangeGraphics, O, A, O, A + Z, R, C, w),
              S(T + 1, E) ||
                this.roundedLine(
                  this.rangeGraphics,
                  O + Z,
                  A,
                  O + Z,
                  A + Z,
                  R,
                  C,
                  w,
                ));
          }
      };
    x(l, d + u, 255, 1, 10);
    const v = Sl(t, n, r);
    if (v) {
      const S = (C, w) => v.has(`${s + C},${o + w}`);
      let b = 0;
      for (const C of v) {
        const [w, R] = C.split(",").map(Number);
        b = Math.max(b, Math.abs(w - s), Math.abs(R - o));
      }
      x(S, b, 16711680, 1, 10);
    } else {
      const S = actionRadiusForKind(t.kind);
      if (S !== void 0) {
        const b = (w, R) => {
            const E = s + w,
              T = o + R;
            return (
              (t.kind === y.BuilderBot
                ? Math.abs(w) + Math.abs(R) === 1
                : f(w, R) <= S) &&
              E >= 0 &&
              T >= 0 &&
              E < n &&
              T < r
            );
          },
          C = Math.ceil(Math.sqrt(S));
        x(b, C + u, 16711680, 1, 10);
      }
    }
  }
  snapshotPositions() {
    if (!this.replay) return;
    const t = this.getCurrentState();
    if (t) {
      (this.prevPositions.clear(), this.prevStored.clear());
      for (const n of t.entities.values()) {
        if (n.kind === y.BuilderBot) {
          const { x: r, y: s } = this.projection.center(
            n.position.x,
            n.position.y,
          );
          this.prevPositions.set(n.id, { x: r, y: s });
        }
        n.stored && this.prevStored.set(n.id, n.stored);
      }
    }
  }
  centerCamera() {
    if (!this.replay) return;
    const { width: t, height: n } = this.replay.map,
      r = this.cameras.main,
      { cx: s, cy: o, bboxW: i, bboxH: a } = this.projection.cameraBbox(t, n),
      f = Math.min(r.width / i, r.height / a) * 0.9;
    (r.setZoom(f), r.centerOn(s, o));
  }
  renderMap() {
    this.replay &&
      (this.mapLayer.removeAll(!0),
      this.gridGraphics.clear(),
      this.ground.draw({
        scene: this,
        mapLayer: this.mapLayer,
        map: this.replay.map,
        theme: this.theme,
      }));
  }
  renderGrid(t) {
    if (!this.replay) return;
    const { width: n, height: r } = this.replay.map,
      s = new Set();
    let o = 0;
    for (const u of t.entities.values()) {
      if (u.kind === y.BuilderBot) continue;
      const l = u.position.x,
        d = u.position.y,
        p = d * n + l;
      if (((o = (o + p * 2654435761) | 0), u.kind === y.Core))
        for (let g = 0; g <= 1; g++)
          for (let h = 0; h <= 1; h++) s.add((d + g) * n + (l + h));
      else s.add(p);
    }
    if (o === this.lastGridHash) return;
    ((this.lastGridHash = o), this.gridGraphics.clear());
    this.gridGraphics.lineStyle(2, 3813416, 0.5);
    const f = (u, l, d, p) => {
      this.gridGraphics.lineBetween(u * Z, l * Z, d * Z, p * Z);
    };
    for (let u = 0; u <= n; u++) {
      let l = -1;
      for (let d = 0; d <= r; d++) {
        const p = u > 0 && s.has(d * n + (u - 1)),
          g = u < n && s.has(d * n + u);
        (d < r && p && g) || d === r
          ? (l >= 0 && l < d && f(u, l, u, d), (l = -1))
          : l < 0 && (l = d);
      }
    }
    for (let u = 0; u <= r; u++) {
      let l = -1;
      for (let d = 0; d <= n; d++) {
        const p = u > 0 && s.has((u - 1) * n + d),
          g = u < r && s.has(u * n + d);
        (d < n && p && g) || d === n
          ? (l >= 0 && l < d && f(l, u, d, u), (l = -1))
          : l < 0 && (l = d);
      }
    }
  }
  renderTurn() {
    if (!this.replay) return;
    const t = this.getCurrentState();
    if (!t) return;
    (this.tweens.killAll(),
      this.shouldAnimate &&
        this.prevPositions.size > 0 &&
        this.updateBotFacings(t),
      this.entityLayer.removeAll(!0),
      this.entitySprites.clear(),
      this.entityObjects.clear(),
      this.resourceObjects.clear());
    const n = [],
      r = [],
      s = [];
    for (const i of t.entities.values())
      i.kind === y.BuilderBot
        ? s.push(i)
        : i.kind === y.Bridge
          ? r.push(i)
          : n.push(i);
    for (const i of n) this.renderEntity(i);
    for (const i of r) this.renderEntity(i, !0);
    for (const i of r) this.renderEntity(i);
    for (const i of n) {
      const a = i.kind === y.Core,
        f = a ? 2 : 1,
        u = a ? 0.5 : 0,
        { x: l, y: d } = this.projection.center(
          i.position.x + u,
          i.position.y + u,
        ),
        p = f * Z;
      this.addResourceIndicator(l, d, p, i);
    }
    for (const i of r) {
      const { x: a, y: f } = this.projection.center(i.position.x, i.position.y);
      this.addResourceIndicator(a, f, Z, i);
    }
    for (const i of s) this.renderEntity(i);
    (this.entityLayer.sort("depth"),
      this.shouldAnimate &&
        this.prevPositions.size > 0 &&
        this.animateMovedEntities(t),
      (this.shouldAnimate = !1),
      this.renderGrid(t),
      this.renderIndicators(t.indicatorLines, t.indicatorDots),
      this.renderBuilderActions(t.builderActions),
      this.renderTileOutlineEvents(t.tileOutlineEvents),
      this.renderTurretFires(t.turretFires));
    const o = this.botStepMode
      ? Math.max(0, this.currentTurn - 1)
      : this.currentTurn;
    if (
      (this.onTurnChange?.(o, this.replay.totalTurns),
      this.onStateChange?.(t),
      this.botStepMode &&
        this.onSubStepChange?.(this.currentSubStep - 1, this.getMaxSubSteps()),
      this.botStepMode)
    ) {
      const i = this.getCurrentSubStepBotId();
      if (i >= 0) {
        const a = t.entities.get(i);
        a &&
          ((this.selectedEntityId = i),
          (this.selectedTile = { x: a.position.x, y: a.position.y }));
      }
    }
    (this.emitSelectInfo(),
      this.hoveredTile &&
        this.onHoverChange?.(
          this.buildTileInfo(this.hoveredTile.x, this.hoveredTile.y),
        ),
      this.drawHighlights());
  }
  isMovementAdjacentToFacing(t, n, r, s) {
    switch (r) {
      case "front":
        return n > 0;
      case "back":
        return n < 0;
      case "side":
        return s ? t > 0 : t < 0;
    }
  }
  updateBotFacings(t) {
    for (const n of t.entities.values()) {
      if (n.kind !== y.BuilderBot) continue;
      const r = n.position.x,
        s = n.position.y,
        o = this.prevBotTiles.get(n.id);
      if ((this.prevBotTiles.set(n.id, { x: r, y: s }), !o)) continue;
      const i = r - o.x,
        a = s - o.y;
      if (i === 0 && a === 0) continue;
      const f = Ya(i, a),
        u = f === "side" && i > 0,
        d = this.botFacings.get(n.id);
      if (!d) {
        this.botFacings.set(n.id, { facing: f, flipX: u });
        continue;
      }
      this.isMovementAdjacentToFacing(i, a, d.facing, d.flipX) ||
        ((d.facing = f), (d.flipX = u));
    }
  }
  animateMovedEntities(t) {
    for (const a of t.entities.values()) {
      if (a.kind !== y.BuilderBot) continue;
      const f = this.prevPositions.get(a.id);
      if (!f) continue;
      const { x: u, y: l } = this.projection.center(a.position.x, a.position.y),
        d = u - f.x,
        p = l - f.y;
      if (d === 0 && p === 0) continue;
      const g = this.entityObjects.get(a.id);
      if (!(!g || g.length === 0))
        for (const h of g) {
          const x = h;
          if (x.x === void 0) continue;
          const v = x.x,
            S = x.y;
          ((x.x = v - d),
            (x.y = S - p),
            this.tweens.add({
              targets: x,
              x: v,
              y: S,
              duration: this.animationDuration,
              ease: "Linear",
            }));
        }
    }
    if (this.botStepMode && this.getCurrentSubStepBotId() !== -2) return;
    const s =
        (this.replay?.rawTurnUpdates[this.currentTurn] ?? []).find(
          (a) => a.distributeResources,
        )?.distributeResources?.moves ?? [],
      o = this.replay.map.width,
      i = new Map();
    for (const a of t.entities.values())
      if (a.kind !== y.BuilderBot)
        if (a.kind === y.Core)
          for (let f = 0; f <= 1; f++)
            for (let u = 0; u <= 1; u++)
              i.set((a.position.y + f) * o + (a.position.x + u), a);
        else i.set(a.position.y * o + a.position.x, a);
    for (const a of s) {
      if (!a.from || !a.to) continue;
      const f = i.get(a.from.y * o + a.from.x),
        u = i.get(a.to.y * o + a.to.x);
      if (!u) continue;
      const { x: l, y: d } = this.projection.center(a.from.x, a.from.y),
        { x: p, y: g } = this.projection.center(a.to.x, a.to.y),
        h = p - l,
        x = g - d;
      if (h === 0 && x === 0) continue;
      if (u.kind === y.Core) {
        const S = a.resolvedResourceType || void 0;
        if (!S) continue;
        const b = Math.round(Z * 0.55),
          C = this.resolveResourceTextureKey(S);
        let w;
        const R = 1e6;
        if (C && this.textures.exists(C)) {
          const E = this.add.sprite(l, d, C),
            T = E.frame.width,
            O = E.frame.height,
            A = Math.min(b / T, b / O);
          (E.setScale(A),
            E.setDepth(R),
            this.entityLayer.add(E),
            (w = E));
        } else {
          const E = kn[S] ?? 16777215,
            T = this.add.circle(l, d, b / 2, E, 0.9);
          (T.setDepth(R), this.entityLayer.add(T), (w = T));
        }
        this.tweens.add({
          targets: w,
          x: p,
          y: g,
          duration: this.animationDuration,
          ease: "Linear",
          onComplete: () => {
            w.destroy();
          },
        });
        continue;
      }
      if (u.kind === y.Foundry) {
        const S =
          a.resolvedResourceType ||
          (f?.kind === y.Harvester ? f.harvesterResourceType : void 0);
        if (!S) continue;
        const b =
            a.resolvedExistingStored !== void 0 &&
            a.resolvedExistingStored !== Oe.None &&
            a.resolvedExistingStored !== Oe.RefinedAxionite
              ? a.resolvedExistingStored
              : void 0,
          C = Math.round(Z * 0.55),
          w = this.resourceObjects.get(u.id);
        for (const A of w ?? []) A.setVisible(!1);
        const R = 1e6;
        let E;
        if (b !== void 0) {
          const A = this.resolveResourceTextureKey(b);
          if (A && this.textures.exists(A)) {
            const j = this.add.sprite(p, g, A);
            (j.setScale(Math.min(C / j.frame.width, C / j.frame.height)),
              j.setDepth(R),
              this.entityLayer.add(j),
              (E = j));
          } else {
            const j = kn[b] ?? 16777215;
            ((E = this.add.circle(p, g, C / 2, j, 0.9)),
              E.setDepth(R),
              this.entityLayer.add(E));
          }
        }
        const T = this.resolveResourceTextureKey(S);
        let O;
        if (T && this.textures.exists(T)) {
          const A = this.add.sprite(l, d, T);
          (A.setScale(Math.min(C / A.frame.width, C / A.frame.height)),
            A.setDepth(R),
            this.entityLayer.add(A),
            (O = A));
        } else {
          const A = kn[S] ?? 16777215;
          ((O = this.add.circle(l, d, C / 2, A, 0.9)),
            O.setDepth(R),
            this.entityLayer.add(O));
        }
        this.tweens.add({
          targets: O,
          x: p,
          y: g,
          duration: this.animationDuration,
          ease: "Linear",
          onComplete: () => {
            (O.destroy(), E?.destroy());
            for (const A of w ?? []) A.setVisible(!0);
          },
        });
        continue;
      }
      const v = this.resourceObjects.get(u.id);
      if (!(!v || v.length === 0))
        for (const S of v) {
          const b = S;
          if (b.x === void 0) continue;
          const C = b.x,
            w = b.y;
          ((b.x = C - h),
            (b.y = w - x),
            this.tweens.add({
              targets: b,
              x: C,
              y: w,
              duration: this.animationDuration,
              ease: "Linear",
            }));
        }
    }
  }
  renderEntity(t, n = !1) {
    const r = t.kind === y.BuilderBot ? this.botFacings.get(t.id) : void 0,
      s = Ua(t.kind, this.displayTeam(t.team), t.direction, r?.facing),
      o = r?.flipX ? { ...s, flipX: !0 } : s,
      i = t.kind === y.Core,
      a = i ? 2 : 1,
      f = i ? 0.5 : 0,
      { x: u, y: l } = this.projection.center(
        t.position.x + f,
        t.position.y + f,
      ),
      d = a * Z;
    if (t.kind === y.Bridge && t.bridgeTarget) {
      const p = this.displayTeam(t.team) === re.A ? "gold" : "silver",
        g = `bridge_${p}`;
      if (this.textures.exists(g)) {
        const h = t.bridgeTarget.x - t.position.x,
          x = t.bridgeTarget.y - t.position.y,
          v = Math.sqrt(h * h + x * x);
        if (n) {
          const L = `bridge_stand_${p}`,
            k = this.add.sprite(u, l, L);
          (k.setScale(Math.min(Z / k.frame.width, Z / k.frame.height)),
            this.entityLayer.add(k));
          return;
        }
        const S = [],
          b = 512,
          C = v * Z,
          w = Math.min(Z * 0.75, C),
          R = Math.atan2(x, h);
        const E = this.make.sprite({ x: 0, y: 0, key: g, add: !1 }),
          T = Math.min(v * b, E.frame.width);
        (E.setCrop(0, 0, T, E.frame.height),
          E.setScale(Z / b, (Z / b) * 0.7),
          E.setOrigin(0, 0.5));
        const O = Z * 0.7,
          A = Math.ceil(C),
          j = Math.ceil(O),
          $ = `bridge_grad_${A}_${j}_${Math.ceil(w)}`;
        if (!this.textures.exists($)) {
          const L = document.createElement("canvas");
          ((L.width = A), (L.height = j));
          const k = L.getContext("2d"),
            M = k.createLinearGradient(0, 0, A, 0);
          (M.addColorStop(0, "rgba(0,0,0,1)"),
            M.addColorStop(w / A, "rgba(0,0,0,0)"),
            M.addColorStop(1 - w / A, "rgba(0,0,0,0)"),
            M.addColorStop(1, "rgba(0,0,0,1)"),
            (k.fillStyle = M),
            k.fillRect(0, 0, A, j),
            this.textures.addCanvas($, L));
        }
        const P = this.add.renderTexture(u, l, A, j);
        (P.setOrigin(0, 0.5),
          P.setRotation(R),
          P.draw(E, 0, j / 2),
          E.destroy());
        const I = this.make.sprite({ x: 0, y: 0, key: g, add: !1 });
        (I.setCrop(0, 0, T, I.frame.height),
          I.setScale(Z / b, (Z / b) * 0.7),
          I.setOrigin(0, 0.5),
          I.setAlpha(0.6),
          P.draw(I, 0, j / 2),
          I.destroy(),
          P.erase($, 0, 0),
          this.entityLayer.add(P),
          S.push(P),
          t.hp < t.maxHp && t.maxHp > 0 && this.addHpBar(u, l, Z, t, S),
          this.entitySprites.set(t.id, P),
          S.length > 0 && this.entityObjects.set(t.id, S));
        return;
      }
    }
    if (o.placeholder || !this.textures.exists(o.key)) {
      const p = o.placeholder ?? { label: "?", colour: 6710886 };
      this.renderPlaceholder(t, u, l, d, p);
    } else this.renderSprite(t, o, u, l, d);
  }
  renderSprite(t, n, r, s, o) {
    const i = this.add.sprite(r, s, n.key),
      a = this.projection.spriteOrigin();
    (i.setOrigin(a.x, a.y),
      i.setDepth(this.projection.depth(t.position.x, t.position.y)));
    const f = [],
      u = i.frame,
      l = u.width,
      d = u.height,
      p = Math.min(o / l, o / d);
    if (
      (i.setScale(p),
      i.setFlipX(n.flipX),
      t.kind === y.Conveyor || t.kind === y.ArmouredConveyor)
    ) {
      const g = Ka(t.direction ?? ge.West);
      (i.setRotation(g.rotation), i.setFlipX(g.flipX));
    }
    if (
      ((t.kind === y.Conveyor || t.kind === y.ArmouredConveyor) &&
        this.theme === "light" &&
        i.setTint(16777215),
      t.kind === y.BuilderBot)
    ) {
      const g = this.add.ellipse(
        r + 2,
        s + o * 0.38,
        o * 0.6,
        o * 0.18,
        0,
        0.4,
      );
      (this.entityLayer.add(g), f.push(g));
    }
    if (
      (this.entityLayer.add(i),
      this.entitySprites.set(t.id, i),
      f.push(i),
      t.kind === y.BuilderBot)
    ) {
      const g = this.add.sprite(r, s, n.key);
      (g.setScale(p),
        g.setFlipX(n.flipX),
        g.setBlendMode(qe.BlendModes.ADD),
        g.setAlpha(0.45),
        this.entityLayer.add(g),
        f.push(g));
    }
    (t.tled && f.push(this.makeTleOverlay(t, r, s, o)),
      t.hp < t.maxHp && t.maxHp > 0 && this.addHpBar(r, s, o, t, f),
      f.length > 0 && this.entityObjects.set(t.id, f));
  }
  makeTleOverlay(t, n, r, s) {
    const o = this.add.rectangle(n, r, s, s, 16711680, 0.35);
    return (this.entityLayer.add(o), o);
  }
  renderPlaceholder(t, n, r, s, o) {
    const i = this.add.container(n, r),
      a = this.add.rectangle(0, 0, s, s, o.colour, 0.7);
    (a.setStrokeStyle(2, o.colour), i.add(a));
    const f = this.add.text(0, 0, o.label, {
      fontSize: "12px",
      color: "#ffffff",
      fontFamily: "monospace",
    });
    (f.setOrigin(0.5),
      i.add(f),
      this.entityLayer.add(i),
      this.entitySprites.set(t.id, i));
    const u = [i];
    (t.tled && u.push(this.makeTleOverlay(t, n, r, s)),
      t.hp < t.maxHp && t.maxHp > 0 && this.addHpBar(n, r, s, t, u),
      u.length > 0 && this.entityObjects.set(t.id, u));
  }
  resolveResourceTextureKey(t) {
    return t === Oe.RawAxionite
      ? "titanium_ore"
      : t === Oe.Titanium || t === Oe.RefinedAxionite
        ? "titanium"
        : xl[t];
  }
  addResourceIndicator(t, n, r, s) {
    if (s.kind === y.Core || _o.has(s.kind)) return;
    const o = s.stored;
    if (!o) return;
    const i = Math.round(Z * 0.55);
    let a;
    const f = this.projection.depth(s.position.x, s.position.y) + 0.5,
      u = this.resolveResourceTextureKey(o);
    if (u && this.textures.exists(u)) {
      const p = this.add.sprite(t, n, u),
        g = p.frame.width,
        h = p.frame.height,
        x = Math.min(i / g, i / h);
      (p.setScale(x),
        p.setDepth(f),
        this.entityLayer.add(p),
        (a = p));
    } else {
      const p = kn[o] ?? 16777215,
        g = this.add.circle(t, n, i / 2, p, 0.9);
      (g.setDepth(f), this.entityLayer.add(g), (a = g));
    }
    const l = this.entityObjects.get(s.id);
    l ? l.push(a) : this.entityObjects.set(s.id, [a]);
    const d = this.resourceObjects.get(s.id);
    d ? d.push(a) : this.resourceObjects.set(s.id, [a]);
  }
  addHpBar(t, n, r, s, o) {
    const i = r - 6,
      a = 8,
      u = n + r / 2 - 4 - a / 2,
      d =
        (s.kind === y.Core
          ? this.projection.depth(s.position.x + 1, s.position.y + 1) + Is
          : this.projection.depth(s.position.x, s.position.y)) + 0.6,
      p = this.add.rectangle(t, u, i, a, 0, 0.6);
    (p.setDepth(d), this.entityLayer.add(p));
    const g = Math.max(0, s.hp / s.maxHp),
      h = g > 0.5 ? 3075674 : g > 0.25 ? 15777824 : 15740976,
      x = this.add.rectangle(t - i / 2 + (i * g) / 2, u, i * g, a, h, 0.9);
    (x.setDepth(d), this.entityLayer.add(x), o && o.push(p, x));
  }
  renderIndicators(t, n) {
    const r = t.length > 0 || n.length > 0;
    if (
      (!r && !this.indicatorsDrawn) ||
      (this.indicatorGraphics.clear(), (this.indicatorsDrawn = r), !r)
    )
      return;
    const s = this.showAllIndicators ? null : this.getHoverSelectedEntityIds();
    for (const o of t) {
      if (s && !s.has(o.id)) continue;
      const i = (o.r << 16) | (o.g << 8) | o.b,
        { x: a, y: f } = this.projection.center(o.posA.x, o.posA.y),
        { x: u, y: l } = this.projection.center(o.posB.x, o.posB.y);
      (this.indicatorGraphics.lineStyle(10, i, 1),
        this.roundedLine(this.indicatorGraphics, a, f, u, l, 10, i, 1));
    }
    for (const o of n) {
      if (s && !s.has(o.id)) continue;
      const i = (o.r << 16) | (o.g << 8) | o.b,
        { x: a, y: f } = this.projection.center(o.pos.x, o.pos.y),
        u = Z * 0.16;
      (this.indicatorGraphics.fillStyle(i, 0.9),
        this.indicatorGraphics.fillCircle(a, f, u));
    }
  }
  renderBuilderActions(t) {
    const n = t.length > 0;
    if (
      (!n && !this.builderActionsDrawn) ||
      (this.builderActionGraphics.clear(), (this.builderActionsDrawn = n), !n)
    )
      return;
    const r = Z * 0.18;
    for (const s of t) {
      const target = s.targetPos ?? s.pos,
        { x: o, y: i } = this.projection.center(target.x, target.y),
        a = s.kind === "heal" ? 4576107 : 16731469;
      (this.builderActionGraphics.fillStyle(a, 0.28),
        this.builderActionGraphics.fillCircle(o, i, r),
        this.builderActionGraphics.lineStyle(4, a, 0.8),
        this.builderActionGraphics.strokeCircle(o, i, r));
    }
  }
  drawTileOutlineRect(t, n, r, s, o, i, a) {
    (t.lineStyle(a, i, 0.95),
      this.roundedLine(t, n, r, n + s, r, a, i, 0.95),
      this.roundedLine(t, n + s, r, n + s, r + o, a, i, 0.95),
      this.roundedLine(t, n + s, r + o, n, r + o, a, i, 0.95),
      this.roundedLine(t, n, r + o, n, r, a, i, 0.95));
  }
  renderTileOutlineEvents(t) {
    const n = t.length > 0;
    if (
      (!n && !this.tileOutlineEventsDrawn) ||
      (this.tileOutlineGraphics.clear(), (this.tileOutlineEventsDrawn = n), !n)
    )
      return;
    const r = 6,
      s = 8;
    for (const i of t) {
      const a = i.kind === "build" ? 7796125 : 16741749;
      const f = i.pos.x * Z + r,
        u = i.pos.y * Z + r,
        l = i.tileSpan * Z - r * 2;
      this.drawTileOutlineRect(this.tileOutlineGraphics, f, u, l, l, a, s);
    }
  }
  renderTurretFires(t) {
    const n = t && t.length > 0;
    if (
      !(!n && !this.turretFiresDrawn) &&
      (this.turretFireGraphics.clear(), (this.turretFiresDrawn = !!n), !!n)
    )
      for (const r of t) {
        const { x: s, y: o } = this.projection.center(r.from.x, r.from.y),
          { x: i, y: a } = this.projection.center(r.to.x, r.to.y);
        (this.turretFireGraphics.lineStyle(10, 16777215, 0.7),
          this.turretFireGraphics.lineBetween(s, o, i, a),
          r.turretKind === y.Breach &&
            (this.turretFireGraphics.fillStyle(16765562, 0.18),
            this.turretFireGraphics.fillCircle(i, a, vl)));
      }
  }
  getHoverSelectedEntityIds() {
    const t = new Set(),
      n = this.getCurrentState();
    if (!n) return t;
    const r = this.hoveredTile?.x,
      s = this.hoveredTile?.y,
      o = r !== void 0 && s !== void 0;
    let i,
      a,
      f = !1;
    if (
      (this.selectedEntityId !== null
        ? t.add(this.selectedEntityId)
        : this.selectedTile &&
          ((i = this.selectedTile.x), (a = this.selectedTile.y), (f = !0)),
      !o && !f)
    )
      return t;
    for (const u of n.entities.values()) {
      const l = u.position.x,
        d = u.position.y;
      (o && l === r && d === s && t.add(u.id),
        f && l === i && d === a && t.add(u.id),
        u.kind === y.Core &&
          (o &&
            r - l >= 0 &&
            r - l <= 1 &&
            s - d >= 0 &&
            s - d <= 1 &&
            t.add(u.id),
          f &&
            i - l >= 0 &&
            i - l <= 1 &&
            a - d >= 0 &&
            a - d <= 1 &&
            t.add(u.id)));
    }
    return t;
  }
}
const $o = "#15100b",
  Go = "#ffffff";
function wl(e, t, n) {
  return {
    type: qe.WEBGL,
    parent: e,
    backgroundColor: n === "light" ? Go : $o,
    scale: { mode: qe.Scale.RESIZE, width: "100%", height: "100%" },
    render: {
      antialias: !0,
      antialiasGL: !0,
      mipmapFilter: "LINEAR_MIPMAP_LINEAR",
      roundPixels: !0,
      desynchronized: !1,
      preserveDrawingBuffer: !0,
    },
    audio: { noAudio: !0 },
    loader: t ? { baseURL: t } : void 0,
    scene: [fn],
  };
}
const Uo = m.forwardRef(function ({ assetBaseUrl: t, theme: n }, s) {
  const o = m.useRef(n),
    a = m.useRef(null),
    f = m.useRef(null),
    u = m.useRef(null),
    l = m.useRef([]);
  return (
    m.useImperativeHandle(s, () => ({
      getScene() {
        return u.current;
      },
      whenReady(d) {
        u.current?.isCreated() ? d(u.current) : l.current.push(d);
      },
      getCanvas() {
        return f.current?.canvas ?? null;
      },
      getGame() {
        return f.current;
      },
    })),
    m.useEffect(() => {
      ((o.current = n),
        u.current?.isCreated() && u.current.setTheme(n ?? "dark"));
    }, [n]),
    m.useEffect(() => {
      const d = a.current;
      if (!d || f.current) return;
      const p = wl(d, t, o.current),
        g = new qe.Game(p);
      f.current = g;
      const h = new ResizeObserver((x) => {
        const S = x[0]?.contentRect;
        if (!f.current || !S) return;
        const { width: b, height: C } = S;
        b > 0 &&
          C > 0 &&
          (f.current.scale.resize(b, C), f.current.scale.refresh());
      });
      return (
        h.observe(d),
        g.events.on("ready", () => {
          const x = g.scene.getScene("GameScene");
          ((u.current = x),
            x.events.once("create", () => {
              x.setTheme(o.current ?? "dark");
              for (const v of l.current) v(x);
              l.current = [];
            }));
        }),
        () => {
          (h.disconnect(),
            f.current?.destroy(!0),
            (f.current = null),
            (u.current = null),
            (l.current = []));
        }
      );
    }, []),
    c.jsx("div", { ref: a, className: "h-full w-full overflow-hidden" })
  );
});
function Cl({ teamALabel: e, teamBLabel: t, teamA: n, teamB: r }) {
  const s = new Map(n.slices.map((a) => [a.id, a])),
    o = new Map(r.slices.map((a) => [a.id, a])),
    i = Tl(n.slices, r.slices);
  return c.jsxs("div", {
    className:
      "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-2",
    children: [
      c.jsxs("div", {
        className: "mb-2 flex items-center justify-between",
        children: [
          c.jsx("span", {
            className: "text-[10px] font-medium text-[var(--vis-text-3)]",
            children: "Scaling Breakdown",
          }),
          c.jsx("span", {
            className: "text-[9px] text-[var(--vis-text-4)]",
            children: "Current turn",
          }),
        ],
      }),
      c.jsxs("div", {
        className: "grid grid-cols-2 gap-3",
        children: [
          c.jsx(Ds, { label: e, accent: "#ffbf40", data: n }),
          c.jsx(Ds, { label: t, accent: "#6eaaff", data: r }),
        ],
      }),
      i.length > 0 &&
        c.jsxs("div", {
          className:
            "mt-3 rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-card)] px-2 py-2",
          children: [
            c.jsxs("div", {
              className:
                "mb-1 grid grid-cols-[minmax(0,1fr)_2.75rem_2.75rem] gap-1 text-[9px] text-[var(--vis-text-4)]",
              children: [
                c.jsx("span", { children: "Unit type" }),
                c.jsx("span", {
                  className: "text-center",
                  style: { color: "#ffbf40" },
                  title: e,
                  children: "G",
                }),
                c.jsx("span", {
                  className: "text-center",
                  style: { color: "#6eaaff" },
                  title: t,
                  children: "S",
                }),
              ],
            }),
            i.map((a) =>
              c.jsxs(
                "div",
                {
                  className:
                    "grid grid-cols-[minmax(0,1fr)_2.75rem_2.75rem] gap-1 py-0.5 text-[10px] text-[var(--vis-text-2)]",
                  children: [
                    c.jsxs("span", {
                      className:
                        "flex min-w-0 items-start gap-1.5 leading-tight",
                      children: [
                        c.jsx("span", {
                          className:
                            "mt-[0.15rem] h-2 w-2 flex-none rounded-full",
                          style: { backgroundColor: a.colour },
                        }),
                        c.jsx("span", {
                          className: "min-w-0 break-words",
                          children: a.label,
                        }),
                      ],
                    }),
                    c.jsx("span", {
                      className: "text-center tabular-nums",
                      children: Ls(s.get(a.id)?.value ?? 0),
                    }),
                    c.jsx("span", {
                      className: "text-center tabular-nums",
                      children: Ls(o.get(a.id)?.value ?? 0),
                    }),
                  ],
                },
                a.id,
              ),
            ),
          ],
        }),
    ],
  });
}
function Ds({ label: e, accent: t, data: n }) {
  const r = El(n.slices);
  return c.jsxs("div", {
    className:
      "flex flex-col items-center rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-card)] px-2 py-2",
    children: [
      c.jsx("div", {
        className: "mb-2 max-w-full truncate text-[10px] font-medium",
        style: { color: t },
        title: e,
        children: e,
      }),
      c.jsxs("div", {
        className: "relative h-24 w-24",
        children: [
          c.jsx("div", {
            className:
              "absolute inset-0 rounded-full border border-[var(--vis-border)] bg-[var(--vis-bg-elevated)]",
            style: r ? { backgroundImage: r } : void 0,
          }),
          c.jsx("div", {
            className:
              "absolute inset-[22px] flex items-center justify-center rounded-full border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] text-center",
            children: c.jsxs("div", {
              className: "leading-tight",
              children: [
                c.jsxs("div", {
                  className:
                    "text-[11px] font-semibold tabular-nums text-[var(--vis-text-1)]",
                  children: [n.totalScale, "%"],
                }),
                c.jsx("div", {
                  className: "text-[9px] text-[var(--vis-text-4)]",
                  children: "total",
                }),
              ],
            }),
          }),
        ],
      }),
      c.jsxs("div", {
        className: "mt-2 text-[9px] text-[var(--vis-text-4)]",
        children: [
          c.jsxs("span", {
            className: "tabular-nums text-[var(--vis-text-2)]",
            children: ["+", n.totalBonus],
          }),
          " bonus",
        ],
      }),
    ],
  });
}
function Tl(e, t) {
  const n = new Map();
  for (const r of e)
    n.set(r.id, { id: r.id, label: r.label, colour: r.colour });
  for (const r of t)
    n.has(r.id) || n.set(r.id, { id: r.id, label: r.label, colour: r.colour });
  return [...n.values()];
}
function El(e) {
  const t = e.filter((o) => o.value > 0),
    n = t.reduce((o, i) => o + i.value, 0);
  if (n <= 0) return;
  let r = 0;
  return `conic-gradient(${t
    .map((o, i) => {
      const a = i === t.length - 1 ? 360 - r : (o.value / n) * 360,
        f = r + a,
        u = `${o.colour} ${r}deg ${f}deg`;
      return ((r = f), u);
    })
    .join(", ")})`;
}
function Ls(e) {
  return e > 0 ? `+${e}` : "0";
}
const st = { top: 6, right: 4, bottom: 18, left: 32 };
function en({
  title: e,
  series: t,
  currentTurn: n,
  maxTurn: r,
  height: s,
  yFloor: o,
}) {
  const i = m.useRef(null),
    a = el(),
    f = m.useCallback(() => {
      const l = i.current;
      if (!l) return;
      const d = l.getContext("2d");
      if (!d) return;
      const p = window.devicePixelRatio || 1,
        g = l.getBoundingClientRect();
      ((l.width = g.width * p), (l.height = g.height * p), d.scale(p, p));
      const h = g.width,
        x = g.height;
      d.clearRect(0, 0, h, x);
      const v = h - st.left - st.right,
        S = x - st.top - st.bottom;
      if (r <= 0 || t.length === 0 || v <= 0 || S <= 0) return;
      const b = Math.min(n, r);
      let C = 1 / 0,
        w = -1 / 0;
      for (const k of t)
        for (let M = 0; M <= b && M < k.data.length; M++) {
          const H = k.data[M];
          (H < C && (C = H), H > w && (w = H));
        }
      (o !== void 0 && (C = Math.min(C, o)), C === w && (w += 1));
      const R = w - C,
        E = R / 4,
        T = Math.pow(10, Math.floor(Math.log10(E))),
        O = [1, 2, 5, 10].map((k) => k * T).find((k) => R / k <= 5) ?? T * 10,
        A = Math.max(O, 10),
        j = o !== void 0 ? o : Math.floor(C / A) * A,
        $ = w * 1.05 + A * 0.1,
        P = (k) => st.left + (k / Math.max(b, 1)) * v,
        I = (k) => st.top + S - ((k - j) / ($ - j)) * S,
        L = [];
      for (let k = j; k <= w + A * 0.01; k += A) L.push(Math.round(k));
      ((d.strokeStyle = a === "dark" ? "#342720" : "#d4bc98"),
        (d.lineWidth = 0.5));
      for (const k of L) {
        const M = I(k);
        (d.beginPath(),
          d.moveTo(st.left, M),
          d.lineTo(st.left + v, M),
          d.stroke());
      }
      ((d.fillStyle = a === "dark" ? "#7a6a50" : "#9a8468"),
        (d.font = "9px monospace"),
        (d.textAlign = "right"),
        (d.textBaseline = "middle"));
      for (const k of L) d.fillText(Rl(k), st.left - 3, I(k));
      ((d.fillStyle = a === "dark" ? "#7a6a50" : "#9a8468"),
        (d.font = "8px monospace"),
        (d.textAlign = "center"),
        (d.textBaseline = "top"),
        d.fillText("0", st.left, st.top + S + 3),
        d.fillText(String(b), st.left + v, st.top + S + 3));
      for (const k of t) {
        ((d.strokeStyle = k.colour),
          (d.lineWidth = 1.2),
          k.dashed ? d.setLineDash([3, 3]) : d.setLineDash([]),
          d.beginPath());
        let M = !1;
        for (let H = 0; H <= b && H < k.data.length; H++) {
          const N = P(H),
            D = I(k.data[H]);
          M ? d.lineTo(N, D) : (d.moveTo(N, D), (M = !0));
        }
        (d.stroke(), d.setLineDash([]));
      }
      for (const k of t)
        if (b < k.data.length) {
          const M = P(b),
            H = I(k.data[b]);
          ((d.fillStyle = k.colour),
            d.beginPath(),
            d.arc(M, H, 2.5, 0, Math.PI * 2),
            d.fill());
        }
    }, [t, n, r, o, a]);
  (m.useEffect(() => {
    f();
  }, [f]),
    m.useEffect(() => {
      const l = i.current;
      if (!l) return;
      const d = new ResizeObserver(() => f());
      return (d.observe(l), () => d.disconnect());
    }, [f]));
  const u = s === void 0 || s === "100%";
  return c.jsxs("div", {
    className:
      "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-2",
    style: u
      ? { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }
      : void 0,
    children: [
      c.jsxs("div", {
        className: "mb-1 flex items-center justify-between",
        children: [
          c.jsx("span", {
            className: "text-[10px] font-medium text-[var(--vis-text-3)]",
            children: e,
          }),
          t.some((l) => l.label) &&
            c.jsx("div", {
              className: "flex gap-2",
              children: t.map((l, d) =>
                l.label
                  ? c.jsxs(
                      "span",
                      {
                        className:
                          "flex items-center gap-1 text-[9px] text-[var(--vis-text-2)]",
                        children: [
                          c.jsx("span", {
                            className: "inline-block h-[6px] w-3 rounded-sm",
                            style: {
                              backgroundColor: l.colour,
                              borderBottom: l.dashed
                                ? `1px dashed ${l.colour}`
                                : void 0,
                            },
                          }),
                          l.label,
                        ],
                      },
                      d,
                    )
                  : null,
              ),
            }),
        ],
      }),
      u
        ? c.jsx("div", {
            style: { flex: 1, minHeight: 0, position: "relative" },
            children: c.jsx("canvas", {
              ref: i,
              "aria-label": "Time series graph",
              style: {
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
              },
              className: "block",
            }),
          })
        : c.jsx("div", {
            style: { width: "100%", height: s, position: "relative" },
            children: c.jsx("canvas", {
              ref: i,
              "aria-label": "Time series graph",
              style: {
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
              },
              className: "block",
            }),
          }),
    ],
  });
}
function Rl(e) {
  const t = Math.round(e);
  return Math.abs(t) >= 1e3 ? `${(t / 1e3).toFixed(1)}k` : String(t);
}
function teamDisplayLabel(e, t) {
  const n = typeof t === "string" ? t.trim() : "";
  return !n || n.toLowerCase() === e.toLowerCase() ? e : `${e} (${n})`;
}
function kl(e, t, n) {
  if (e.winner === null) return "Draw";
  const r = n ? (e.winner === re.A ? re.B : re.A) : e.winner;
  return t
    ? r === re.A
      ? `${t.match.teamAName} wins`
      : `${t.match.teamBName} wins`
    : r === re.A
      ? "Team Gold wins"
      : "Team Silver wins";
}
const Wo = {
  [y.BuilderBot]: "Bots",
  [y.Conveyor]: "Conveyors",
  [y.Splitter]: "Splitters",
  [y.Harvester]: "Harvesters",
  [y.Barrier]: "Barriers",
  [y.Gunner]: "Gunners",
  [y.Sentinel]: "Sentinels",
  [y.Launcher]: "Launchers",
};
function Al(e) {
  const t = {};
  for (const n of e.entities.values())
    (t[n.kind] || (t[n.kind] = [0, 0]), t[n.kind][n.team === re.A ? 0 : 1]++);
  return t;
}
const Ko = {
    [y.BuilderBot]: 20,
    [y.Barrier]: 1,
    [y.Conveyor]: 1,
    [y.Splitter]: 1,
    [y.Harvester]: 5,
    [y.Gunner]: 10,
    [y.Sentinel]: 20,
    [y.Launcher]: 10,
  },
  Ol = [
    y.BuilderBot,
    y.Barrier,
    y.Conveyor,
    y.Splitter,
    y.Harvester,
    y.Gunner,
    y.Sentinel,
    y.Launcher,
  ],
  jl = {
    [y.BuilderBot]: "#f59e0b",
    [y.Barrier]: "#f97316",
    [y.Conveyor]: "#60a5fa",
    [y.Splitter]: "#34d399",
    [y.Harvester]: "#22c55e",
    [y.Gunner]: "#ef4444",
    [y.Sentinel]: "#06b6d4",
    [y.Launcher]: "#eab308",
  };
function Fs(e, t) {
  const n = new Map();
  for (const o of e.entities.values()) {
    if (o.team !== t) continue;
    const i = Ko[o.kind] ?? 0;
    i <= 0 || n.set(o.kind, (n.get(o.kind) ?? 0) + i);
  }
  const r = Ol.map((o) => ({
      id: o,
      label: Wo[o] ?? o,
      colour: jl[o] ?? "#94a3b8",
      value: n.get(o) ?? 0,
    })),
    s = r.reduce((o, i) => o + i.value, 0);
  return { slices: r, totalBonus: s, totalScale: 100 + s };
}
function Vo({
  replay: e,
  loading: t,
  fileName: n,
  turn: r,
  maxTurn: s,
  gameState: o,
  onFileUpload: i,
  onFileDrop: a,
  scrollable: f = !0,
  matchData: u,
  selectedGameNumber: l,
  loadingMatch: d,
  loadingGame: p,
  matchError: g,
  onLoadMatch: h,
  onSelectGame: x,
  initialMatchId: v,
  tournamentMode: S,
  revealedGames: b,
  swapTeams: C,
}) {
  const w = o?.players,
    [R, E] = m.useState(!1),
    [T, O] = m.useState(v ?? "");
  m.useEffect(() => {
    v !== void 0 && O(v);
  }, [v]);
  const [A, j] = m.useState(null);
  m.useEffect(() => {
    j(null);
    if (!e) {
      return;
    }
    const W = requestAnimationFrame(() => {
      j(e.computeTimeSeries(Ko));
    });
    return () => cancelAnimationFrame(W);
  }, [e]);
  const $ = m.useMemo(() => (o ? Al(o) : null), [o]),
    P = m.useMemo(() => {
      if (!o) return null;
      const W = C ? re.B : re.A,
        B = C ? re.A : re.B;
      return { teamA: Fs(o, W), teamB: Fs(o, B) };
    }, [o, C]),
    I = C ? A?.titaniumB : A?.titaniumA,
    L = C ? A?.titaniumA : A?.titaniumB,
    ammoA = C ? A?.ammoB : A?.ammoA,
    ammoB = C ? A?.ammoA : A?.ammoB,
    k = C ? A?.titaniumCollectedB : A?.titaniumCollectedA,
    M = C ? A?.titaniumCollectedA : A?.titaniumCollectedB,
    H = C ? A?.scaleB : A?.scaleA,
    N = C ? A?.scaleA : A?.scaleB,
    D = C ? A?.harvestersB : A?.harvestersA,
    U = C ? A?.harvestersA : A?.harvestersB,
    Q = m.useMemo(
      () =>
        !I || !L
          ? []
          : [
              { label: "Gold", colour: "#ffbf40", data: I },
              { label: "Silver", colour: "#6eaaff", data: L },
            ],
      [I, L],
    ),
    ammoSeries = m.useMemo(
      () =>
        !ammoA || !ammoB
          ? []
          : [
              { label: "Gold", colour: "#ffbf40", data: ammoA },
              { label: "Silver", colour: "#6eaaff", data: ammoB },
            ],
      [ammoA, ammoB],
    ),
    ve = m.useMemo(
      () =>
        !k || !M
          ? []
          : [
              { label: "Gold", colour: "#ffbf40", data: k },
              { label: "Silver", colour: "#6eaaff", data: M },
            ],
      [k, M],
    ),
    Y = m.useMemo(
      () =>
        !H || !N
          ? []
          : [
              { label: "Gold", colour: "#ffbf40", data: H },
              { label: "Silver", colour: "#6eaaff", data: N },
            ],
      [H, N],
    ),
    J = m.useMemo(
      () =>
        !D || !U
          ? []
          : [
              { label: "Gold", colour: "#ffbf40", data: D },
              { label: "Silver", colour: "#6eaaff", data: U },
            ],
      [D, U],
    ),
    ce = m.useCallback((W) => {
      (W.preventDefault(), E(!0));
    }, []),
    z = m.useCallback((W) => {
      (W.preventDefault(), E(!1));
    }, []),
    ue = m.useCallback(
      (W) => {
        (W.preventDefault(), E(!1));
        const B = W.dataTransfer.files[0];
        B && a(B);
      },
      [a],
    ),
    X = m.useCallback(
      (W) => {
        (W.preventDefault(), T.trim() && h && h(T.trim()));
      },
      [T, h],
    ),
    te = u?.match.teamAName ?? "Gold",
    ye = u?.match.teamBName ?? "Silver";
  return c.jsxs("aside", {
    className: `flex h-full w-full flex-shrink-0 flex-col gap-4 p-4${f ? " overflow-y-auto" : ""}`,
    children: [
      h &&
        c.jsxs("section", {
          children: [
            c.jsx("h2", {
              className:
                "mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
              children: "Match",
            }),
            !S &&
              c.jsxs("form", {
                onSubmit: X,
                className: "flex gap-2",
                children: [
                  c.jsx("input", {
                    type: "text",
                    "aria-label": "Match ID",
                    placeholder: "Match ID",
                    value: T,
                    onChange: (W) => O(W.target.value),
                    className:
                      "min-w-0 flex-1 rounded-lg border border-[var(--vis-border-2)] bg-[var(--vis-bg-panel)] px-2 py-1.5 text-xs text-[var(--vis-text-1)] placeholder-[var(--vis-text-4)] outline-none focus:border-[#ffbf40]",
                  }),
                  c.jsx("button", {
                    type: "submit",
                    disabled: d || !T.trim(),
                    className:
                      "rounded-lg bg-[#ffbf40] px-3 py-1.5 text-xs font-semibold text-black hover:bg-[#ffa800] disabled:opacity-30",
                    children: d ? "..." : "Go",
                  }),
                ],
              }),
            g &&
              c.jsx("p", {
                className: "mt-2 text-xs text-red-400",
                children: g,
              }),
            u &&
              c.jsxs("div", {
                className: "mt-3 flex flex-col gap-2",
                children: [
                  c.jsxs("div", {
                    className:
                      "flex items-center justify-between rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-card)] px-3 py-2",
                    children: [
                      c.jsx("span", {
                        className:
                          "max-w-[40%] truncate text-xs font-medium text-[#ffbf40]",
                        children: te,
                      }),
                      c.jsx("span", {
                        className:
                          "text-sm font-bold tabular-nums text-[var(--vis-text-1)]",
                        children: S
                          ? (() => {
                              let W = 0,
                                B = 0;
                              for (const G of u.games) {
                                if (!b?.has(G.gameNumber)) continue;
                                const ne =
                                    (G.winnerId != null &&
                                      G.winnerId === u.match.teamAId) ||
                                    G.winnerSide === "a",
                                  de =
                                    (G.winnerId != null &&
                                      G.winnerId === u.match.teamBId) ||
                                    G.winnerSide === "b";
                                (ne && W++, de && B++);
                              }
                              return b && b.size > 0 ? `${W}–${B}` : "?–?";
                            })()
                          : `${u.match.scoreA}–${u.match.scoreB}`,
                      }),
                      c.jsx("span", {
                        className:
                          "max-w-[40%] truncate text-right text-xs font-medium text-[#6eaaff]",
                        children: ye,
                      }),
                    ],
                  }),
                  c.jsx("div", {
                    className: "flex flex-col gap-1",
                    children: u.games.map((W) => {
                      const B = W.gameNumber === l,
                        G = !S || b?.has(W.gameNumber),
                        ne =
                          (W.winnerId != null &&
                            W.winnerId === u.match.teamAId) ||
                          W.winnerSide === "a",
                        de =
                          (W.winnerId != null &&
                            W.winnerId === u.match.teamBId) ||
                          W.winnerSide === "b",
                        se = ne ? "#ffbf40" : de ? "#6eaaff" : void 0,
                        q = ne ? te : de ? ye : null;
                      return c.jsxs(
                        "button",
                        {
                          onClick: () => x?.(W.gameNumber),
                          disabled: !W.replayS3Key || p,
                          className: `flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-all ${B ? "border border-[#ffbf40]/40 bg-[#ffbf40]/15 text-[var(--vis-text-1)]" : "border border-transparent text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated)] hover:text-[var(--vis-text-1)]"} disabled:cursor-not-allowed disabled:opacity-30`,
                          children: [
                            c.jsx("span", {
                              className:
                                "w-4 font-mono tabular-nums text-[var(--vis-text-3)]",
                              children: W.gameNumber,
                            }),
                            c.jsx("span", {
                              className: "flex-1 truncate",
                              children: W.mapName,
                            }),
                            G && q && se
                              ? c.jsx("span", {
                                  className:
                                    "max-w-[4rem] truncate text-[10px]",
                                  style: { color: se },
                                  children: q,
                                })
                              : S
                                ? c.jsx("span", {
                                    className:
                                      "text-[10px] text-[var(--vis-text-4)]",
                                    children: "???",
                                  })
                                : null,
                            G &&
                              W.turnsPlayed != null &&
                              c.jsxs("span", {
                                className:
                                  "tabular-nums text-[10px] text-[var(--vis-text-4)]",
                                children: [W.turnsPlayed, "t"],
                              }),
                          ],
                        },
                        W.gameNumber,
                      );
                    }),
                  }),
                ],
              }),
          ],
        }),
      c.jsxs("section", {
        children: [
          c.jsx("h2", {
            className:
              "mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
            children: "Replay File",
          }),
          c.jsxs("label", {
            className: `flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-4 text-sm transition-all ${t ? "pointer-events-none border-[#ffbf40]/40 bg-[var(--vis-bg-badge)]" : R ? "border-[#ffbf40] bg-[var(--vis-bg-elevated)] text-[var(--vis-text-1)]" : "border-[var(--vis-border-2)] bg-[var(--vis-bg-panel)] text-[var(--vis-text-3)] hover:border-[#ffbf40] hover:text-[var(--vis-text-1)]"}`,
            onDragOver: ce,
            onDragLeave: z,
            onDrop: ue,
            children: [
              t
                ? c.jsxs(c.Fragment, {
                    children: [
                      c.jsxs("svg", {
                        className: "h-5 w-5 animate-spin text-[#ffbf40]",
                        viewBox: "0 0 24 24",
                        fill: "none",
                        children: [
                          c.jsx("circle", {
                            className: "opacity-25",
                            cx: "12",
                            cy: "12",
                            r: "10",
                            stroke: "currentColor",
                            strokeWidth: "3",
                          }),
                          c.jsx("path", {
                            className: "opacity-75",
                            fill: "currentColor",
                            d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z",
                          }),
                        ],
                      }),
                      c.jsx("span", {
                        className: "text-[#ffbf40]",
                        children: "Decoding replay...",
                      }),
                    ],
                  })
                : c.jsxs(c.Fragment, {
                    children: [
                      c.jsxs("svg", {
                        className: "h-5 w-5",
                        viewBox: "0 0 24 24",
                        fill: "none",
                        stroke: "currentColor",
                        strokeWidth: "2",
                        strokeLinecap: "round",
                        strokeLinejoin: "round",
                        children: [
                          c.jsx("path", {
                            d: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4",
                          }),
                          c.jsx("polyline", { points: "17 8 12 3 7 8" }),
                          c.jsx("line", {
                            x1: "12",
                            y1: "3",
                            x2: "12",
                            y2: "15",
                          }),
                        ],
                      }),
                      c.jsx("span", {
                        children: e
                          ? "Load another replay"
                          : "Drop .replay26 file or click to upload",
                      }),
                    ],
                  }),
              c.jsx("input", {
                type: "file",
                accept:
                  ".replay26,.map26,.pb,application/x-protobuf,application/octet-stream",
                "aria-label": "Upload replay file",
                className: "hidden",
                onChange: i,
                disabled: t,
              }),
            ],
          }),
          n &&
            e &&
            c.jsx("p", {
              className: "mt-2 truncate text-xs text-[var(--vis-text-3)]",
              title: n,
              children: n,
            }),
        ],
      }),
      e &&
        r === s &&
        c.jsx("div", {
          className:
            "rounded-xl border border-[#ffbf40]/30 bg-[var(--vis-bg-winner)] px-3 py-2 text-center text-sm font-medium text-[#ffbf40]",
          children: kl(e, u, C),
        }),
      c.jsxs("section", {
        className: "flex flex-col gap-3",
        children: [
          c.jsx("h2", {
            className:
              "text-xs font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
            children: "Teams",
          }),
          [re.A, re.B].map((W) => {
            const B = C ? (W === re.A ? re.B : re.A) : W,
              G = w?.[B],
              ne = W === re.A ? te : ye,
              de = W === re.A ? "#ffbf40" : "#6eaaff",
              se = teamDisplayLabel(W === re.A ? "Gold" : "Silver", ne);
            return c.jsxs(
              "div",
              {
                className:
                  "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3 text-sm",
                children: [
                  c.jsxs("div", {
                    className: "mb-2 flex items-center gap-2",
                    children: [
                      c.jsx("div", {
                        className: "h-3 w-3 rounded-full",
                        style: { backgroundColor: de },
                      }),
                      c.jsx("span", {
                        className: "font-medium text-[var(--vis-text-1)]",
                        children: se,
                      }),
                    ],
                  }),
                  G
                    ? c.jsx("div", {
                        className: "flex flex-col gap-2",
                        children: c.jsxs("div", {
                          className:
                            "grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-[var(--vis-text-2)]",
                          children: [
                            c.jsx("span", { children: "Titanium" }),
                            c.jsx("span", {
                              className: "text-right tabular-nums",
                              children: G.titanium,
                            }),
                            c.jsx("span", { children: "Ammo" }),
                            c.jsx("span", {
                              className: "text-right tabular-nums",
                              children: G.ammo ?? 0,
                            }),
                            c.jsx("span", { children: "Ti collected" }),
                            c.jsx("span", {
                              className: "text-right tabular-nums",
                              children: G.titaniumCollected,
                            }),
                          ],
                        }),
                      })
                    : c.jsx("span", {
                        className: "text-xs text-[var(--vis-text-3)]",
                        children: "—",
                      }),
                ],
              },
              W,
            );
          }),
        ],
      }),
      o &&
        c.jsxs("section", {
          children: [
            c.jsx("h2", {
              className:
                "mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
              children: "Entity Counts",
            }),
            c.jsxs("div", {
              className:
                "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3 text-xs",
              children: [
                c.jsxs("div", {
                  className:
                    "mb-1 grid grid-cols-[1fr_2rem_2rem] gap-1 text-[var(--vis-text-3)]",
                  children: [
                    c.jsx("span", {}),
                    c.jsx("span", {
                      className: "text-center",
                      style: { color: "#ffbf40" },
                      children: "G",
                    }),
                    c.jsx("span", {
                      className: "text-center",
                      style: { color: "#6eaaff" },
                      children: "S",
                    }),
                  ],
                }),
                Object.entries(Wo).map(([W, B]) => {
                  const G = $?.[W] ?? [0, 0],
                    ne = C ? G[1] : G[0],
                    de = C ? G[0] : G[1];
                  return c.jsxs(
                    "div",
                    {
                      className:
                        "grid grid-cols-[1fr_2rem_2rem] gap-1 text-[var(--vis-text-2)]",
                      children: [
                        c.jsx("span", { children: B }),
                        c.jsx("span", {
                          className: "text-center tabular-nums",
                          children: ne,
                        }),
                        c.jsx("span", {
                          className: "text-center tabular-nums",
                          children: de,
                        }),
                      ],
                    },
                    W,
                  );
                }),
              ],
            }),
          ],
        }),
      e &&
        A &&
        c.jsxs("section", {
          className: "flex flex-col gap-2",
          children: [
            c.jsx("h2", {
              className:
                "text-xs font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
              children: "Graphs",
            }),
            c.jsx(en, {
              title: "Titanium",
              series: Q,
              currentTurn: r,
              maxTurn: s,
              height: 96,
              yFloor: 0,
            }),
            c.jsx(en, {
              title: "Ammunition",
              series: ammoSeries,
              currentTurn: r,
              maxTurn: s,
              height: 96,
              yFloor: 0,
            }),
            c.jsx(en, {
              title: "Titanium Collected",
              series: ve,
              currentTurn: r,
              maxTurn: s,
              height: 96,
              yFloor: 0,
            }),
            c.jsx(en, {
              title: "Scaling Factor %",
              series: Y,
              currentTurn: r,
              maxTurn: s,
              height: 96,
              yFloor: 100,
            }),
            c.jsx(en, {
              title: "Harvesters",
              series: J,
              currentTurn: r,
              maxTurn: s,
              height: 96,
              yFloor: 0,
            }),
            P &&
              c.jsx(Cl, {
                teamALabel: te,
                teamBLabel: ye,
                teamA: P.teamA,
                teamB: P.teamB,
              }),
          ],
        }),
    ],
  });
}
const Il = {
    [y.Core]: "Core",
    [y.BuilderBot]: "Builder Bot",
    [y.Conveyor]: "Conveyor",
    [y.Splitter]: "Splitter",
    [y.Harvester]: "Harvester",
    [y.Barrier]: "Barrier",
    [y.Gunner]: "Gunner",
    [y.Sentinel]: "Sentinel",
    [y.Launcher]: "Launcher",
  },
  Nl = {
    [Qe.Empty]: "Empty",
    [Qe.Wall]: "Wall",
    [Qe.OreTitanium]: "Titanium Ore",
  },
  Pl = {
    [ge.Centre]: "Centre",
    [ge.North]: "North",
    [ge.Northeast]: "Northeast",
    [ge.East]: "East",
    [ge.Southeast]: "Southeast",
    [ge.South]: "South",
    [ge.Southwest]: "Southwest",
    [ge.West]: "West",
    [ge.Northwest]: "Northwest",
  },
  Sr = {
    [Oe.None]: "None",
    [Oe.Titanium]: "Titanium",
  },
  Bl = {
    [re.A]: { label: "Team Gold", colour: "#ffbf40" },
    [re.B]: { label: "Team Silver", colour: "#6eaaff" },
  },
  Ml = {
    [re.A]: { label: "Team Silver", colour: "#6eaaff" },
    [re.B]: { label: "Team Gold", colour: "#ffbf40" },
  };
function Dl({ entity: e, swapTeams: t }) {
  const n = (t ? Ml : Bl)[e.team],
    r = [],
    s = e.kind === y.Gunner || e.kind === y.Sentinel || e.kind === y.Launcher;
  return (
    r.push({ label: "ID", value: `${e.id}` }),
    r.push({ label: "Team", value: n.label }),
    r.push({ label: "Position", value: `(${e.position.x}, ${e.position.y})` }),
    r.push({ label: "HP", value: `${e.hp} / ${e.maxHp}` }),
    e.direction !== void 0 &&
      r.push({
        label: "Direction",
        value: Pl[e.direction] ?? `${e.direction}`,
      }),
    e.stored &&
      e.kind !== y.BuilderBot &&
      !s &&
      r.push({ label: "Stored", value: Sr[e.stored] ?? `${e.stored}` }),
    e.ammoType &&
      (e.ammoAmount ?? 0) > 0 &&
      r.push({
        label: "Ammo",
        value: `${Sr[e.ammoType] ?? e.ammoType} x${e.ammoAmount ?? 0}`,
      }),
    e.actionCooldown !== void 0 &&
      r.push({ label: "Action CD", value: `${e.actionCooldown}` }),
    e.kind === y.BuilderBot &&
      r.push({ label: "Move CD", value: `${e.moveCooldown ?? 0}` }),
    e.harvesterResourceType &&
      r.push({
        label: "Harvests",
        value: Sr[e.harvesterResourceType] ?? `${e.harvesterResourceType}`,
      }),
    e.harvesterCooldown !== void 0 &&
      r.push({ label: "Cooldown", value: `${e.harvesterCooldown}` }),
    e.execTimeUs !== void 0 &&
      r.push({
        label: "Exec Time",
        value: e.tled ? `${e.execTimeUs} μs (TLE!)` : `${e.execTimeUs} μs`,
        ...(e.tled && { className: "text-red-400 font-semibold" }),
      }),
    c.jsxs("div", {
      className:
        "rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-card)] p-2.5",
      children: [
        c.jsxs("div", {
          className: "mb-1.5 flex items-center gap-2",
          children: [
            c.jsx("span", {
              className: "inline-block h-2.5 w-2.5 rounded-full",
              style: { backgroundColor: n.colour },
            }),
            c.jsx("span", {
              className: "text-xs font-semibold text-[var(--vis-text-1)]",
              children: Il[e.kind] ?? e.kind,
            }),
          ],
        }),
        c.jsx("div", {
          className: "grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]",
          children: r.map((o) =>
            c.jsxs(
              "div",
              {
                className: "contents",
                children: [
                  c.jsx("span", {
                    className: "text-[var(--vis-text-3)]",
                    children: o.label,
                  }),
                  c.jsx("span", {
                    className: o.className ?? "text-[var(--vis-text-2)]",
                    children: o.value,
                  }),
                ],
              },
              o.label,
            ),
          ),
        }),
        e.stdout &&
          c.jsxs("div", {
            className: "mt-2",
            children: [
              c.jsx("div", {
                className:
                  "mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
                children: "stdout",
              }),
              c.jsx("pre", {
                className:
                  "max-h-40 overflow-y-auto whitespace-pre-wrap break-all rounded bg-[var(--vis-bg-code)] p-1.5 text-[10px] text-[var(--vis-text-2)]",
                children: e.stdout,
              }),
            ],
          }),
      ],
    })
  );
}
function Hs({ info: e, label: t, swapTeams: n }) {
  return c.jsxs("div", {
    children: [
      c.jsxs("div", {
        className: "mb-1.5 flex items-baseline justify-between",
        children: [
          c.jsx("h3", {
            className:
              "text-[11px] font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
            children: t,
          }),
          c.jsxs("span", {
            className: "text-[11px] text-[var(--vis-text-4)]",
            children: ["(", e.pos.x, ", ", e.pos.y, ")"],
          }),
        ],
      }),
      c.jsx("div", {
        className: "mb-2 text-[11px] text-[var(--vis-text-4)]",
        children: Nl[e.environment] ?? "Unknown",
      }),
      e.entities.length === 0
        ? c.jsx("div", {
            className: "text-xs text-[var(--vis-text-4)] italic",
            children: "No entities",
          })
        : c.jsx("div", {
            className: "flex flex-col gap-2",
            children: e.entities.map((r) =>
              c.jsx(Dl, { entity: r, swapTeams: n }, r.id),
            ),
          }),
    ],
  });
}
function Ll({
  selectedTile: e,
  hoveredTile: t,
  showAllIndicators: n,
  onToggleShowAllIndicators: r,
  swapTeams: l,
}) {
  const d = t && !(e && t.pos.x === e.pos.x && t.pos.y === e.pos.y);
  return c.jsxs("aside", {
    className:
      "flex w-full flex-shrink-0 flex-col gap-4 p-3 sm:p-4 lg:h-full lg:overflow-y-auto",
    children: [
      c.jsxs("section", {
        className:
          "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3",
        children: [
          c.jsx("h3", {
            className:
              "mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
            children: "Indicators",
          }),
          c.jsx("div", {
            className: "flex flex-col gap-1.5",
            children: c.jsx(Rt, {
              label: "Show all indicators",
              checked: n,
              onChange: r,
            }),
          }),
        ],
      }),
      e &&
        c.jsx("section", {
          className:
            "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3",
          children: c.jsx(Hs, { info: e, label: "Selected", swapTeams: l }),
        }),
      e &&
        d &&
        c.jsx("div", { className: "border-t border-[var(--vis-border)]" }),
      d &&
        c.jsx("section", {
          className:
            "rounded-xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3",
          children: c.jsx(Hs, { info: t, label: "Hovered", swapTeams: l }),
        }),
    ],
  });
}
function Rt({ label: e, checked: t, onChange: n }) {
  return c.jsxs("label", {
    className:
      "flex cursor-pointer items-center gap-2 text-[11px] text-[var(--vis-text-2)] select-none",
    children: [
      c.jsx("input", {
        type: "checkbox",
        "aria-label": e,
        checked: t,
        onChange: (r) => n(r.target.checked),
        className: "accent-[#ffbf40]",
      }),
      e,
    ],
  });
}
function Fl({
  replay: e,
  loading: t,
  fileName: n,
  turn: r,
  maxTurn: s,
  gameState: o,
  onFileUpload: i,
  onFileDrop: a,
  matchData: f,
  selectedGameNumber: u,
  loadingMatch: l,
  loadingGame: d,
  matchError: p,
  onLoadMatch: g,
  onSelectGame: h,
  initialMatchId: x,
  tournamentMode: v,
  revealedGames: S,
  swapTeams: b,
  showAllIndicators: C,
  onToggleShowAllIndicators: w,
}) {
  return c.jsxs("div", {
    className:
      "flex h-full w-full min-h-0 flex-col gap-3 overflow-y-auto overscroll-none rounded-2xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3 pb-4 sm:gap-4 sm:p-4 sm:pb-6",
    children: [
      c.jsxs("div", {
        className: "rounded-xl p-4",
        children: [
          c.jsx("h3", {
            className:
              "mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
            children: "Indicators",
          }),
          c.jsx("div", {
            className: "flex flex-col gap-1.5",
            children: c.jsx(Rt, {
              label: "Show all indicators",
              checked: C,
              onChange: w,
            }),
          }),
        ],
      }),
      c.jsx("div", {
        children: c.jsx(Vo, {
          replay: e,
          loading: t,
          fileName: n,
          turn: r,
          maxTurn: s,
          gameState: o,
          onFileUpload: i,
          onFileDrop: a,
          matchData: f,
          selectedGameNumber: u,
          loadingMatch: l,
          loadingGame: d,
          matchError: p,
          onLoadMatch: g,
          onSelectGame: h,
          initialMatchId: x,
          scrollable: !1,
          tournamentMode: v,
          revealedGames: S,
          swapTeams: b,
        }),
      }),
    ],
  });
}
function Yo({ selectedTile: e, hoveredTile: t, swapTeams: n }) {
  const r = {
      [Qe.Empty]: "Empty",
      [Qe.Wall]: "Wall",
      [Qe.OreTitanium]: "Titanium Ore",
    },
    s = {
      [y.Core]: "Core",
      [y.BuilderBot]: "Builder Bot",
      [y.Conveyor]: "Conveyor",
      [y.Splitter]: "Splitter",
      [y.Harvester]: "Harvester",
      [y.Barrier]: "Barrier",
      [y.Gunner]: "Gunner",
      [y.Sentinel]: "Sentinel",
      [y.Launcher]: "Launcher",
    },
    o = {
      [ge.Centre]: "Centre",
      [ge.North]: "North",
      [ge.Northeast]: "Northeast",
      [ge.East]: "East",
      [ge.Southeast]: "Southeast",
      [ge.South]: "South",
      [ge.Southwest]: "Southwest",
      [ge.West]: "West",
      [ge.Northwest]: "Northwest",
    },
    i = {
      [Oe.None]: "None",
      [Oe.Titanium]: "Titanium",
    },
    a = n
      ? {
          [re.A]: { label: "Team Silver", colour: "#6eaaff" },
          [re.B]: { label: "Team Gold", colour: "#ffbf40" },
        }
      : {
          [re.A]: { label: "Team Gold", colour: "#ffbf40" },
          [re.B]: { label: "Team Silver", colour: "#6eaaff" },
        },
    f = ({ entity: l }) => {
      const d = a[l.team],
        p = [],
        g =
          l.kind === y.Gunner || l.kind === y.Sentinel || l.kind === y.Launcher;
      return (
        p.push({ label: "ID", value: `${l.id}` }),
        p.push({ label: "Team", value: d.label }),
        p.push({
          label: "Position",
          value: `(${l.position.x}, ${l.position.y})`,
        }),
        p.push({ label: "HP", value: `${l.hp} / ${l.maxHp}` }),
        l.direction !== void 0 &&
          p.push({
            label: "Direction",
            value: o[l.direction] ?? `${l.direction}`,
          }),
        l.stored &&
          l.kind !== y.BuilderBot &&
          !g &&
          p.push({ label: "Stored", value: i[l.stored] ?? `${l.stored}` }),
        l.ammoType &&
          (l.ammoAmount ?? 0) > 0 &&
          p.push({
            label: "Ammo",
            value: `${i[l.ammoType] ?? l.ammoType} x${l.ammoAmount ?? 0}`,
          }),
        l.actionCooldown !== void 0 &&
          p.push({ label: "Action CD", value: `${l.actionCooldown}` }),
        l.kind === y.BuilderBot &&
          p.push({ label: "Move CD", value: `${l.moveCooldown ?? 0}` }),
        l.harvesterResourceType &&
          p.push({
            label: "Harvests",
            value: i[l.harvesterResourceType] ?? `${l.harvesterResourceType}`,
          }),
        l.harvesterCooldown !== void 0 &&
          p.push({ label: "Cooldown", value: `${l.harvesterCooldown}` }),
        l.execTimeUs !== void 0 &&
          p.push({
            label: "Exec Time",
            value: l.tled ? `${l.execTimeUs} μs (TLE!)` : `${l.execTimeUs} μs`,
            ...(l.tled && { className: "text-red-400 font-semibold" }),
          }),
        c.jsxs("div", {
          className:
            "rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-card)] p-2.5",
          children: [
            c.jsxs("div", {
              className: "mb-1.5 flex items-center gap-2",
              children: [
                c.jsx("span", {
                  className: "inline-block h-2.5 w-2.5 rounded-full",
                  style: { backgroundColor: d.colour },
                }),
                c.jsx("span", {
                  className: "text-xs font-semibold text-[var(--vis-text-1)]",
                  children: s[l.kind] ?? l.kind,
                }),
              ],
            }),
            c.jsx("div", {
              className:
                "grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]",
              children: p.map((h) =>
                c.jsxs(
                  "div",
                  {
                    className: "contents",
                    children: [
                      c.jsx("span", {
                        className: "text-[var(--vis-text-3)]",
                        children: h.label,
                      }),
                      c.jsx("span", {
                        className: h.className ?? "text-[var(--vis-text-2)]",
                        children: h.value,
                      }),
                    ],
                  },
                  h.label,
                ),
              ),
            }),
            l.stdout &&
              c.jsxs("div", {
                className: "mt-2",
                children: [
                  c.jsx("div", {
                    className:
                      "mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--vis-text-3)]",
                    children: "stdout",
                  }),
                  c.jsx("pre", {
                    className:
                      "max-h-40 overflow-y-auto whitespace-pre-wrap break-all rounded bg-[var(--vis-bg-code)] p-1.5 text-[10px] text-[var(--vis-text-2)]",
                    children: l.stdout,
                  }),
                ],
              }),
          ],
        })
      );
    },
    u = t && !(t.pos.x === e.pos.x && t.pos.y === e.pos.y);
  return c.jsx("div", {
    className: "absolute inset-x-3 bottom-3 z-50 flex justify-start",
    children: c.jsxs("div", {
      className:
        "max-w-xl rounded-2xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] p-3 shadow-xl shadow-black/30",
      children: [
        c.jsxs("div", {
          className:
            "mb-1 flex items-center justify-between text-[11px] text-[var(--vis-text-3)]",
          children: [
            c.jsx("span", {
              className:
                "font-semibold uppercase tracking-wider text-[#ffbf40]",
              children: "Clicked",
            }),
            c.jsxs("span", { children: ["(", e.pos.x, ", ", e.pos.y, ")"] }),
          ],
        }),
        c.jsx("div", {
          className: "mb-2 text-[11px] text-[var(--vis-text-4)]",
          children: r[e.environment] ?? "Unknown",
        }),
        e.entities.length === 0
          ? c.jsx("div", {
              className: "text-xs italic text-[var(--vis-text-4)]",
              children: "No entities",
            })
          : c.jsx("div", {
              className: "flex max-h-[40vh] flex-col gap-2 overflow-y-auto",
              children: e.entities.map((l) => c.jsx(f, { entity: l }, l.id)),
            }),
        u &&
          c.jsxs(c.Fragment, {
            children: [
              c.jsx("div", {
                className: "my-2 border-t border-[var(--vis-border)]",
              }),
              c.jsxs("div", {
                className:
                  "mb-1 flex items-center justify-between text-[11px] text-[var(--vis-text-3)]",
                children: [
                  c.jsx("span", {
                    className:
                      "font-semibold uppercase tracking-wider text-[#6eaaff]",
                    children: "Hovered",
                  }),
                  c.jsxs("span", {
                    children: ["(", t.pos.x, ", ", t.pos.y, ")"],
                  }),
                ],
              }),
              c.jsx("div", {
                className: "mb-2 text-[11px] text-[var(--vis-text-4)]",
                children: r[t.environment] ?? "Unknown",
              }),
              t.entities.length === 0
                ? c.jsx("div", {
                    className: "text-xs italic text-[var(--vis-text-4)]",
                    children: "No entities",
                  })
                : c.jsx("div", {
                    className:
                      "flex max-h-[30vh] flex-col gap-2 overflow-y-auto",
                    children: t.entities.map((l) =>
                      c.jsx(f, { entity: l }, l.id),
                    ),
                  }),
            ],
          }),
      ],
    }),
  });
}
function Hl({
  replay: e,
  turn: t,
  maxTurn: n,
  playing: r,
  speed: s,
  botStepMode: o,
  subStep: i,
  maxSubSteps: a,
  onPrev: f,
  onNext: u,
  onPlayPause: l,
  onSliderChange: d,
  onTurnInput: p,
  onSpeedUp: g,
  onSlowDown: h,
  onToggleBotStepMode: x,
}) {
  const [v, S] = m.useState(""),
    [b, C] = m.useState(!1);
  m.useEffect(() => {
    r && C(!1);
  }, [r]);
  const w = m.useCallback(
    (R) => {
      const E = parseInt(R, 10);
      (isNaN(E) || p(E), C(!1));
    },
    [p],
  );
  return c.jsxs("div", {
    className:
      "flex flex-shrink-0 flex-wrap justify-center items-center gap-2 rounded-2xl border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] px-2.5 py-2 sm:gap-3 sm:px-4",
    children: [
      c.jsx("button", {
        className: `grid h-8 flex-shrink-0 place-items-center rounded-lg px-2 text-xs font-semibold transition-all ${o ? "bg-[#ffbf40] text-black hover:bg-[#ffa800]" : "bg-[var(--vis-bg-elevated)] text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)]"} disabled:opacity-30`,
        title: o
          ? "Disable bot-step mode"
          : "Enable bot-step mode (step through individual bot turns)",
        onClick: x,
        disabled: !e,
        children: "Bot Step",
      }),
      c.jsx("button", {
        className:
          "grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-[var(--vis-bg-elevated)] text-xs font-semibold text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)] disabled:opacity-30",
        title: "Half speed",
        onClick: h,
        disabled: !e || s <= 1,
        children: "½x",
      }),
      c.jsx("button", {
        className:
          "grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-[var(--vis-bg-elevated)] text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)] disabled:opacity-30",
        title: o ? "Previous bot step" : "Previous turn",
        onClick: f,
        disabled: !e || (t <= 0 && (!o || i <= 0)) || r,
        children: "◀",
      }),
      c.jsx("button", {
        className:
          "grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-[#ffbf40] font-bold text-black hover:bg-[#ffa800] disabled:opacity-30",
        title: r ? "Pause" : "Play",
        onClick: l,
        disabled: !e,
        children: r ? "❚❚" : "▶",
      }),
      c.jsx("button", {
        className:
          "grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-[var(--vis-bg-elevated)] text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)] disabled:opacity-30",
        title: o ? "Next bot step" : "Next turn",
        onClick: u,
        disabled: !e || (t >= n && (!o || i >= a)) || r,
        children: "▶",
      }),
      c.jsx("button", {
        className:
          "grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-[var(--vis-bg-elevated)] text-xs font-semibold text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)] disabled:opacity-30",
        title: "Double speed",
        onClick: g,
        disabled: !e || s >= 256,
        children: "2x",
      }),
      c.jsxs("span", {
        className: "flex-shrink-0 text-xs text-[var(--vis-text-3)]",
        children: [s, "x"],
      }),
      c.jsx("input", {
        type: "range",
        "aria-label": "Turn",
        min: 0,
        max: n || 1,
        value: t,
        onChange: d,
        className:
          "order-3 w-full accent-[#ffbf40] md:order-none md:min-w-0 md:flex-1",
        disabled: !e,
      }),
      c.jsxs("div", {
        className:
          "order-4 flex w-full flex-shrink-0 items-center justify-end gap-2 text-xs text-[var(--vis-text-3)] md:order-none md:w-auto md:justify-start",
        children: [
          e
            ? b
              ? c.jsxs("form", {
                  className: "flex items-center gap-1",
                  onSubmit: (R) => {
                    (R.preventDefault(), w(v));
                  },
                  children: [
                    c.jsx("input", {
                      type: "number",
                      "aria-label": "Go to turn",
                      min: 0,
                      max: n,
                      ref: (R) => R?.focus(),
                      value: v,
                      onChange: (R) => S(R.target.value),
                      onBlur: () => w(v),
                      className:
                        "w-14 rounded bg-[var(--vis-bg-elevated)] px-1 py-0.5 text-right text-xs text-[var(--vis-text-1)] outline-none ring-1 ring-[#ffbf40] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
                    }),
                    c.jsxs("span", { children: ["/ ", n] }),
                  ],
                })
              : c.jsxs("button", {
                  className:
                    "rounded bg-[var(--vis-bg-elevated)] px-2 py-0.5 tabular-nums text-[var(--vis-text-2)] transition-all hover:bg-[var(--vis-bg-elevated-hover)] hover:text-[var(--vis-text-1)] hover:ring-1 hover:ring-[#ffbf40]/50 cursor-text disabled:opacity-50 disabled:cursor-default disabled:hover:bg-[var(--vis-bg-elevated)] disabled:hover:text-[var(--vis-text-2)] disabled:hover:ring-0",
                  onClick: () => {
                    (S(String(t)), C(!0));
                  },
                  title: "Click to type a turn number",
                  disabled: r,
                  children: [
                    t,
                    " ",
                    c.jsx("span", {
                      className: "text-[var(--vis-text-3)]",
                      children: "/",
                    }),
                    " ",
                    n,
                  ],
                })
            : "0 / —",
          o &&
            e &&
            a > 0 &&
            c.jsxs("span", {
              className:
                "rounded bg-[var(--vis-bg-badge)] px-2 py-0.5 tabular-nums text-[#ffbf40]",
              children: [
                "step ",
                i,
                c.jsx("span", {
                  className: "text-[var(--vis-text-3)]",
                  children: "/",
                }),
                a,
              ],
            }),
        ],
      }),
    ],
  });
}
const _s = {};
function jt(e, t) {
  const n = m.useRef(_s);
  return (n.current === _s && (n.current = e(t)), n);
}
const $r = [];
let Gr;
function _l() {
  return Gr;
}
function $l(e) {
  $r.push(e);
}
function Xo(e) {
  const t = (n, r) => {
    const s = jt(Ul).current;
    let o;
    try {
      Gr = s;
      for (const i of $r) i.before(s);
      o = e(n, r);
      for (const i of $r) i.after(s);
      s.didInitialize = !0;
    } finally {
      Gr = void 0;
    }
    return o;
  };
  return ((t.displayName = e.displayName || e.name), t);
}
function Gl(e) {
  return m.forwardRef(Xo(e));
}
function Ul() {
  return { didInitialize: !1 };
}
function zo(e) {
  const t = m.useRef(!0);
  t.current && ((t.current = !1), e());
}
const Wl = () => {},
  xe = typeof document < "u" ? m.useLayoutEffect : Wl;
function Kl(e, t) {
  return function (r, ...s) {
    const o = new URL(e);
    return (
      o.searchParams.set("code", r.toString()),
      s.forEach((i) => o.searchParams.append("args[]", i)),
      `${t} error #${r}; visit ${o} for the full message.`
    );
  };
}
const It = Kl("https://base-ui.com/production-error", "Base UI"),
  qo = m.createContext(void 0);
function vn(e) {
  const t = m.useContext(qo);
  if (t === void 0 && !e) throw new Error(It(72));
  return t;
}
const Vl = [];
function ts(e) {
  m.useEffect(e, Vl);
}
const cn = 0;
class pt {
  static create() {
    return new pt();
  }
  currentId = cn;
  start(t, n) {
    (this.clear(),
      (this.currentId = setTimeout(() => {
        ((this.currentId = cn), n());
      }, t)));
  }
  isStarted() {
    return this.currentId !== cn;
  }
  clear = () => {
    this.currentId !== cn &&
      (clearTimeout(this.currentId), (this.currentId = cn));
  };
  disposeEffect = () => this.clear;
}
function Lt() {
  const e = jt(pt.create).current;
  return (ts(e.disposeEffect), e);
}
const on = typeof navigator < "u",
  wr = zl(),
  Zo = Zl(),
  Qo = ql(),
  Jo =
    typeof CSS > "u" || !CSS.supports
      ? !1
      : CSS.supports("-webkit-backdrop-filter:none"),
  Yl =
    wr.platform === "MacIntel" && wr.maxTouchPoints > 1
      ? !0
      : /iP(hone|ad|od)|iOS/.test(wr.platform),
  ei = on && /apple/i.test(navigator.vendor),
  Ur = (on && /android/i.test(Zo)) || /android/i.test(Qo),
  Xl = on && Zo.toLowerCase().startsWith("mac") && !navigator.maxTouchPoints,
  ti = Qo.includes("jsdom/");
function zl() {
  if (!on) return { platform: "", maxTouchPoints: -1 };
  const e = navigator.userAgentData;
  return e?.platform
    ? { platform: e.platform, maxTouchPoints: navigator.maxTouchPoints }
    : {
        platform: navigator.platform ?? "",
        maxTouchPoints: navigator.maxTouchPoints ?? -1,
      };
}
function ql() {
  if (!on) return "";
  const e = navigator.userAgentData;
  return e && Array.isArray(e.brands)
    ? e.brands.map(({ brand: t, version: n }) => `${t}/${n}`).join(" ")
    : navigator.userAgent;
}
function Zl() {
  if (!on) return "";
  const e = navigator.userAgentData;
  return e?.platform ? e.platform : (navigator.platform ?? "");
}
function Ql(e) {
  (e.preventDefault(), e.stopPropagation());
}
function Jl(e) {
  return "nativeEvent" in e;
}
function ec(e) {
  return e.pointerType === "" && e.isTrusted
    ? !0
    : Ur && e.pointerType
      ? e.type === "click" && e.buttons === 1
      : e.detail === 0 && !e.pointerType;
}
function tc(e) {
  return ti
    ? !1
    : (!Ur && e.width === 0 && e.height === 0) ||
        (Ur &&
          e.width === 1 &&
          e.height === 1 &&
          e.pressure === 0 &&
          e.detail === 0 &&
          e.pointerType === "mouse") ||
        (e.width < 1 &&
          e.height < 1 &&
          e.pressure === 0 &&
          e.detail === 0 &&
          e.pointerType === "touch");
}
function mn(e, t) {
  const n = ["mouse", "pen"];
  return (n.push("", void 0), n.includes(e));
}
function nc(e) {
  const t = e.type;
  return t === "click" || t === "mousedown" || t === "keydown" || t === "keyup";
}
function Jn() {
  return typeof window < "u";
}
function ze(e) {
  return ns(e) ? (e.nodeName || "").toLowerCase() : "#document";
}
function Ge(e) {
  var t;
  return (
    (e == null || (t = e.ownerDocument) == null ? void 0 : t.defaultView) ||
    window
  );
}
function wt(e) {
  var t;
  return (t = (ns(e) ? e.ownerDocument : e.document) || window.document) == null
    ? void 0
    : t.documentElement;
}
function ns(e) {
  return Jn() ? e instanceof Node || e instanceof Ge(e).Node : !1;
}
function he(e) {
  return Jn() ? e instanceof Element || e instanceof Ge(e).Element : !1;
}
function Le(e) {
  return Jn() ? e instanceof HTMLElement || e instanceof Ge(e).HTMLElement : !1;
}
function rn(e) {
  return !Jn() || typeof ShadowRoot > "u"
    ? !1
    : e instanceof ShadowRoot || e instanceof Ge(e).ShadowRoot;
}
function Ht(e) {
  const { overflow: t, overflowX: n, overflowY: r, display: s } = nt(e);
  return (
    /auto|scroll|overlay|hidden|clip/.test(t + r + n) &&
    s !== "inline" &&
    s !== "contents"
  );
}
function rc(e) {
  return /^(table|td|th)$/.test(ze(e));
}
function er(e) {
  try {
    if (e.matches(":popover-open")) return !0;
  } catch {}
  try {
    return e.matches(":modal");
  } catch {
    return !1;
  }
}
const sc = /transform|translate|scale|rotate|perspective|filter/,
  oc = /paint|layout|strict|content/,
  Wt = (e) => !!e && e !== "none";
let Cr;
function rs(e) {
  const t = he(e) ? nt(e) : e;
  return (
    Wt(t.transform) ||
    Wt(t.translate) ||
    Wt(t.scale) ||
    Wt(t.rotate) ||
    Wt(t.perspective) ||
    (!tr() && (Wt(t.backdropFilter) || Wt(t.filter))) ||
    sc.test(t.willChange || "") ||
    oc.test(t.contain || "")
  );
}
function ic(e) {
  let t = At(e);
  for (; Le(t) && !kt(t); ) {
    if (rs(t)) return t;
    if (er(t)) return null;
    t = At(t);
  }
  return null;
}
function tr() {
  return (
    Cr == null &&
      (Cr =
        typeof CSS < "u" &&
        CSS.supports &&
        CSS.supports("-webkit-backdrop-filter", "none")),
    Cr
  );
}
function kt(e) {
  return /^(html|body|#document)$/.test(ze(e));
}
function nt(e) {
  return Ge(e).getComputedStyle(e);
}
function nr(e) {
  return he(e)
    ? { scrollLeft: e.scrollLeft, scrollTop: e.scrollTop }
    : { scrollLeft: e.scrollX, scrollTop: e.scrollY };
}
function At(e) {
  if (ze(e) === "html") return e;
  const t = e.assignedSlot || e.parentNode || (rn(e) && e.host) || wt(e);
  return rn(t) ? t.host : t;
}
function ni(e) {
  const t = At(e);
  return kt(t)
    ? e.ownerDocument
      ? e.ownerDocument.body
      : e.body
    : Le(t) && Ht(t)
      ? t
      : ni(t);
}
function gn(e, t, n) {
  var r;
  (t === void 0 && (t = []), n === void 0 && (n = !0));
  const s = ni(e),
    o = s === ((r = e.ownerDocument) == null ? void 0 : r.body),
    i = Ge(s);
  if (o) {
    const a = Wr(i);
    return t.concat(
      i,
      i.visualViewport || [],
      Ht(s) ? s : [],
      a && n ? gn(a) : [],
    );
  } else return t.concat(s, gn(s, [], n));
}
function Wr(e) {
  return e.parent && Object.getPrototypeOf(e.parent) ? e.frameElement : null;
}
const Kr = "data-base-ui-focusable",
  ri =
    "input:not([type='hidden']):not([disabled]),[contenteditable]:not([contenteditable='false']),textarea:not([disabled])";
function ft(e) {
  let t = e.activeElement;
  for (; t?.shadowRoot?.activeElement != null; ) t = t.shadowRoot.activeElement;
  return t;
}
function ie(e, t) {
  if (!e || !t) return !1;
  const n = t.getRootNode?.();
  if (e.contains(t)) return !0;
  if (n && rn(n)) {
    let r = t;
    for (; r; ) {
      if (e === r) return !0;
      r = r.parentNode || r.host;
    }
  }
  return !1;
}
function it(e) {
  return "composedPath" in e ? e.composedPath()[0] : e.target;
}
function Hn(e, t) {
  if (!he(e)) return !1;
  const n = e;
  if (t.hasElement(n)) return !n.hasAttribute("data-trigger-disabled");
  for (const [, r] of t.entries())
    if (ie(r, n)) return !r.hasAttribute("data-trigger-disabled");
  return !1;
}
function Tr(e, t) {
  if (t == null) return !1;
  if ("composedPath" in e) return e.composedPath().includes(t);
  const n = e;
  return n.target != null && t.contains(n.target);
}
function ac(e) {
  return e.matches("html,body");
}
function ss(e) {
  return Le(e) && e.matches(ri);
}
function lc(e) {
  return (
    e?.closest(
      `button,a[href],[role="button"],select,[tabindex]:not([tabindex="-1"]),${ri}`,
    ) != null
  );
}
function $s(e) {
  return e ? e.getAttribute("role") === "combobox" && ss(e) : !1;
}
function cc(e) {
  if (!e || ti) return !0;
  try {
    return e.matches(":focus-visible");
  } catch {
    return !0;
  }
}
function Gs(e) {
  return e ? (e.hasAttribute(Kr) ? e : e.querySelector(`[${Kr}]`) || e) : null;
}
function uc(e, t) {
  return t != null && !mn(t) ? 0 : typeof e == "function" ? e() : e;
}
function _n(e, t, n) {
  const r = uc(e, n);
  return typeof r == "number" ? r : r?.[t];
}
function Us(e) {
  return typeof e == "function" ? e() : e;
}
function si(e, t) {
  return t || e === "click" || e === "mousedown";
}
function dc(e) {
  return e?.includes("mouse") && e !== "mousedown";
}
function os() {}
const Xe = Object.freeze({}),
  oi = "none",
  $n = "trigger-press",
  Ze = "trigger-hover",
  Mn = "trigger-focus",
  ii = "outside-press",
  fc = "close-press",
  ai = "focus-out",
  is = "escape-key",
  pc = "disabled",
  li = "imperative-action";
function Be(e, t, n, r) {
  let s = !1,
    o = !1;
  const i = Xe;
  return {
    reason: e,
    event: t ?? new Event("base-ui"),
    cancel() {
      s = !0;
    },
    allowPropagation() {
      o = !0;
    },
    get isCanceled() {
      return s;
    },
    get isPropagationAllowed() {
      return o;
    },
    trigger: n,
    ...i,
  };
}
const ci = m.createContext({
  hasProvider: !1,
  timeoutMs: 0,
  delayRef: { current: 0 },
  initialDelayRef: { current: 0 },
  timeout: new pt(),
  currentIdRef: { current: null },
  currentContextRef: { current: null },
});
function hc(e) {
  const { children: t, delay: n, timeoutMs: r = 0 } = e,
    s = m.useRef(n),
    o = m.useRef(n),
    i = m.useRef(null),
    a = m.useRef(null),
    f = Lt();
  return c.jsx(ci.Provider, {
    value: m.useMemo(
      () => ({
        hasProvider: !0,
        delayRef: s,
        initialDelayRef: o,
        currentIdRef: i,
        timeoutMs: r,
        currentContextRef: a,
        timeout: f,
      }),
      [r, f],
    ),
    children: t,
  });
}
function mc(e, t = { open: !1 }) {
  const { open: n } = t,
    r = "rootStore" in e ? e.rootStore : e,
    s = r.useState("floatingId"),
    o = m.useContext(ci),
    {
      currentIdRef: i,
      delayRef: a,
      timeoutMs: f,
      initialDelayRef: u,
      currentContextRef: l,
      hasProvider: d,
      timeout: p,
    } = o,
    [g, h] = m.useState(!1);
  return (
    xe(() => {
      function x() {
        (h(!1),
          l.current?.setIsInstantPhase(!1),
          (i.current = null),
          (l.current = null),
          (a.current = u.current));
      }
      if (i.current && !n && i.current === s) {
        if ((h(!1), f)) {
          const v = s;
          return (
            p.start(f, () => {
              r.select("open") || (i.current && i.current !== v) || x();
            }),
            () => {
              p.clear();
            }
          );
        }
        x();
      }
    }, [n, s, i, a, f, u, l, p, r]),
    xe(() => {
      if (!n) return;
      const x = l.current,
        v = i.current;
      (p.clear(),
        (l.current = { onOpenChange: r.setOpen, setIsInstantPhase: h }),
        (i.current = s),
        (a.current = { open: 0, close: _n(u.current, "close") }),
        v !== null && v !== s
          ? (h(!0), x?.setIsInstantPhase(!0), x?.onOpenChange(!1, Be(oi)))
          : (h(!1), x?.setIsInstantPhase(!1)));
    }, [n, s, r, i, a, u, l, p]),
    xe(
      () => () => {
        l.current = null;
      },
      [l],
    ),
    m.useMemo(
      () => ({ hasProvider: d, delayRef: a, isInstantPhase: g }),
      [d, a, g],
    )
  );
}
function me(e, t, n, r) {
  return (
    e.addEventListener(t, n, r),
    () => {
      e.removeEventListener(t, n, r);
    }
  );
}
function yt(...e) {
  return () => {
    for (let t = 0; t < e.length; t += 1) {
      const n = e[t];
      n && n();
    }
  };
}
function Gn(e, t, n, r) {
  const s = jt(ui).current;
  return (xc(s, e, t, n, r) && di(s, [e, t, n, r]), s.callback);
}
function gc(e) {
  const t = jt(ui).current;
  return (bc(t, e) && di(t, e), t.callback);
}
function ui() {
  return { callback: null, cleanup: null, refs: [] };
}
function xc(e, t, n, r, s) {
  return (
    e.refs[0] !== t || e.refs[1] !== n || e.refs[2] !== r || e.refs[3] !== s
  );
}
function bc(e, t) {
  return e.refs.length !== t.length || e.refs.some((n, r) => n !== t[r]);
}
function di(e, t) {
  if (((e.refs = t), t.every((n) => n == null))) {
    e.callback = null;
    return;
  }
  e.callback = (n) => {
    if ((e.cleanup && (e.cleanup(), (e.cleanup = null)), n != null)) {
      const r = Array(t.length).fill(null);
      for (let s = 0; s < t.length; s += 1) {
        const o = t[s];
        if (o != null)
          switch (typeof o) {
            case "function": {
              const i = o(n);
              typeof i == "function" && (r[s] = i);
              break;
            }
            case "object": {
              o.current = n;
              break;
            }
          }
      }
      e.cleanup = () => {
        for (let s = 0; s < t.length; s += 1) {
          const o = t[s];
          if (o != null)
            switch (typeof o) {
              case "function": {
                const i = r[s];
                typeof i == "function" ? i() : o(null);
                break;
              }
              case "object": {
                o.current = null;
                break;
              }
            }
        }
      };
    }
  };
}
function et(e) {
  const t = jt(vc, e).current;
  return ((t.next = e), xe(t.effect), t);
}
function vc(e) {
  const t = {
    current: e,
    next: e,
    effect: () => {
      t.current = t.next;
    },
  };
  return t;
}
const as = { ...Xa },
  Er = as.useInsertionEffect,
  yc = Er && Er !== as.useLayoutEffect ? Er : (e) => e();
function Te(e) {
  const t = jt(Sc).current;
  return ((t.next = e), yc(t.effect), t.trampoline);
}
function Sc() {
  const e = {
    next: void 0,
    callback: wc,
    trampoline: (...t) => e.callback?.(...t),
    effect: () => {
      e.callback = e.next;
    },
  };
  return e;
}
function wc() {}
const An = null;
class Cc {
  callbacks = [];
  callbacksCount = 0;
  nextId = 1;
  startId = 1;
  isScheduled = !1;
  tick = (t) => {
    this.isScheduled = !1;
    const n = this.callbacks,
      r = this.callbacksCount;
    if (
      ((this.callbacks = []),
      (this.callbacksCount = 0),
      (this.startId = this.nextId),
      r > 0)
    )
      for (let s = 0; s < n.length; s += 1) n[s]?.(t);
  };
  request(t) {
    const n = this.nextId;
    return (
      (this.nextId += 1),
      this.callbacks.push(t),
      (this.callbacksCount += 1),
      !this.isScheduled &&
        (requestAnimationFrame(this.tick), (this.isScheduled = !0)),
      n
    );
  }
  cancel(t) {
    const n = t - this.startId;
    n < 0 ||
      n >= this.callbacks.length ||
      ((this.callbacks[n] = null), (this.callbacksCount -= 1));
  }
}
const On = new Cc();
class vt {
  static create() {
    return new vt();
  }
  static request(t) {
    return On.request(t);
  }
  static cancel(t) {
    return On.cancel(t);
  }
  currentId = An;
  request(t) {
    (this.cancel(),
      (this.currentId = On.request(() => {
        ((this.currentId = An), t());
      })));
  }
  cancel = () => {
    this.currentId !== An && (On.cancel(this.currentId), (this.currentId = An));
  };
  disposeEffect = () => this.cancel;
}
function fi() {
  const e = jt(vt.create).current;
  return (ts(e.disposeEffect), e);
}
function Ie(e) {
  return e?.ownerDocument || document;
}
const Tc = {
    clipPath: "inset(50%)",
    overflow: "hidden",
    whiteSpace: "nowrap",
    border: 0,
    padding: 0,
    width: 1,
    height: 1,
    margin: -1,
  },
  Ec = { ...Tc, position: "fixed", top: 0, left: 0 },
  Un = m.forwardRef(function (t, n) {
    const [r, s] = m.useState();
    xe(() => {
      ei && s("button");
    }, []);
    const o = { tabIndex: 0, role: r };
    return c.jsx("span", {
      ...t,
      ref: n,
      style: Ec,
      "aria-hidden": r ? void 0 : !0,
      ...o,
      "data-base-ui-focus-guard": "",
    });
  }),
  Rc = ["top", "right", "bottom", "left"],
  sn = Math.min,
  ot = Math.max,
  Wn = Math.round,
  jn = Math.floor,
  St = (e) => ({ x: e, y: e }),
  kc = { left: "right", right: "left", bottom: "top", top: "bottom" };
function Vr(e, t, n) {
  return ot(e, sn(t, n));
}
function Ot(e, t) {
  return typeof e == "function" ? e(t) : e;
}
function tt(e) {
  return e.split("-")[0];
}
function _t(e) {
  return e.split("-")[1];
}
function ls(e) {
  return e === "x" ? "y" : "x";
}
function cs(e) {
  return e === "y" ? "height" : "width";
}
function lt(e) {
  const t = e[0];
  return t === "t" || t === "b" ? "y" : "x";
}
function us(e) {
  return ls(lt(e));
}
function Ac(e, t, n) {
  n === void 0 && (n = !1);
  const r = _t(e),
    s = us(e),
    o = cs(s);
  let i =
    s === "x"
      ? r === (n ? "end" : "start")
        ? "right"
        : "left"
      : r === "start"
        ? "bottom"
        : "top";
  return (t.reference[o] > t.floating[o] && (i = Kn(i)), [i, Kn(i)]);
}
function Oc(e) {
  const t = Kn(e);
  return [Yr(e), t, Yr(t)];
}
function Yr(e) {
  return e.includes("start")
    ? e.replace("start", "end")
    : e.replace("end", "start");
}
const Ws = ["left", "right"],
  Ks = ["right", "left"],
  jc = ["top", "bottom"],
  Ic = ["bottom", "top"];
function Nc(e, t, n) {
  switch (e) {
    case "top":
    case "bottom":
      return n ? (t ? Ks : Ws) : t ? Ws : Ks;
    case "left":
    case "right":
      return t ? jc : Ic;
    default:
      return [];
  }
}
function Pc(e, t, n, r) {
  const s = _t(e);
  let o = Nc(tt(e), n === "start", r);
  return (
    s && ((o = o.map((i) => i + "-" + s)), t && (o = o.concat(o.map(Yr)))),
    o
  );
}
function Kn(e) {
  const t = tt(e);
  return kc[t] + e.slice(t.length);
}
function Bc(e) {
  return { top: 0, right: 0, bottom: 0, left: 0, ...e };
}
function pi(e) {
  return typeof e != "number"
    ? Bc(e)
    : { top: e, right: e, bottom: e, left: e };
}
function Vn(e) {
  const { x: t, y: n, width: r, height: s } = e;
  return {
    width: r,
    height: s,
    top: n,
    left: t,
    right: t + r,
    bottom: n + s,
    x: t,
    y: n,
  };
}
function Mc(e) {
  return e.visibility === "hidden" || e.visibility === "collapse";
}
function hi(e, t = e ? nt(e) : null) {
  return !e || !e.isConnected || !t || Mc(t)
    ? !1
    : typeof e.checkVisibility == "function"
      ? e.checkVisibility()
      : t.display !== "none" && t.display !== "contents";
}
const Dc =
  'a[href],button,input,select,textarea,summary,details,iframe,object,embed,[tabindex],[contenteditable]:not([contenteditable="false"]),audio[controls],video[controls]';
function Lc(e) {
  const t = e.assignedSlot;
  if (t) return t;
  if (e.parentElement) return e.parentElement;
  const n = e.getRootNode();
  return rn(n) ? n.host : null;
}
function Xr(e) {
  for (const t of Array.from(e.children)) if (ze(t) === "summary") return t;
  return null;
}
function Fc(e, t) {
  const n = Xr(t);
  return !!n && (e === n || ie(n, e));
}
function mi(e) {
  const t = e ? ze(e) : "";
  return (
    e != null &&
    e.matches(Dc) &&
    (t !== "summary" ||
      (e.parentElement != null &&
        ze(e.parentElement) === "details" &&
        Xr(e.parentElement) === e)) &&
    (t !== "details" || Xr(e) == null) &&
    (t !== "input" || e.type !== "hidden")
  );
}
function gi(e) {
  if (!mi(e) || !e.isConnected || e.matches(":disabled")) return !1;
  for (let t = e; t; t = Lc(t)) {
    const n = t !== e,
      r = ze(t) === "slot";
    if (
      t.hasAttribute("inert") ||
      (n && ze(t) === "details" && !t.open && !Fc(e, t)) ||
      t.hasAttribute("hidden") ||
      (!r && !Hc(t, n))
    )
      return !1;
  }
  return !0;
}
function Hc(e, t) {
  const n = nt(e);
  return t ? n.display !== "none" : hi(e, n);
}
function xi(e) {
  const t = e.tabIndex;
  if (t < 0) {
    const n = ze(e);
    if (
      n === "details" ||
      n === "audio" ||
      n === "video" ||
      (Le(e) && e.isContentEditable)
    )
      return 0;
  }
  return t;
}
function Rr(e) {
  if (ze(e) !== "input") return null;
  const t = e;
  return t.type === "radio" && t.name !== "" ? t : null;
}
function _c(e, t) {
  const n = Rr(e);
  if (!n) return !0;
  const r = t.find((s) => {
    const o = Rr(s);
    return o?.name === n.name && o.form === n.form && o.checked;
  });
  return r
    ? r === n
    : t.find((s) => {
        const o = Rr(s);
        return o?.name === n.name && o.form === n.form;
      }) === n;
}
function bi(e) {
  if (Le(e) && ze(e) === "slot") {
    const t = e.assignedElements({ flatten: !0 });
    if (t.length > 0) return t;
  }
  return Le(e) && e.shadowRoot
    ? Array.from(e.shadowRoot.children)
    : Array.from(e.children);
}
function vi(e, t) {
  bi(e).forEach((n) => {
    (mi(n) && t.push(n), vi(n, t));
  });
}
function yi(e, t, n) {
  bi(e).forEach((r) => {
    (Le(r) && r.matches(t) && n.push(r), yi(r, t, n));
  });
}
function ds(e) {
  return gi(e) && xi(e) >= 0;
}
function Si(e) {
  const t = [];
  return (vi(e, t), t.filter(gi));
}
function rr(e) {
  const t = Si(e);
  return t.filter((n) => xi(n) >= 0 && _c(n, t));
}
function wi(e, t) {
  const n = rr(e),
    r = n.length;
  if (r === 0) return;
  const s = ft(Ie(e)),
    o = n.indexOf(s),
    i = o === -1 ? (t === 1 ? 0 : r - 1) : o + t;
  return n[i];
}
function Ci(e) {
  return wi(Ie(e).body, 1) || e;
}
function Ti(e) {
  return wi(Ie(e).body, -1) || e;
}
function pn(e, t) {
  const n = t || e.currentTarget,
    r = e.relatedTarget;
  return !r || !ie(n, r);
}
function $c(e) {
  rr(e).forEach((n) => {
    ((n.dataset.tabindex = n.getAttribute("tabindex") || ""),
      n.setAttribute("tabindex", "-1"));
  });
}
function Vs(e) {
  const t = [];
  (yi(e, "[data-tabindex]", t),
    t.forEach((n) => {
      const r = n.dataset.tabindex;
      (delete n.dataset.tabindex,
        r ? n.setAttribute("tabindex", r) : n.removeAttribute("tabindex"));
    }));
}
function Ft(e, t, n = !0) {
  return e
    .filter((s) => s.parentId === t)
    .flatMap((s) => [...(!n || s.context?.open ? [s] : []), ...Ft(e, s.id, n)]);
}
function Ys(e, t) {
  let n = [],
    r = e.find((s) => s.id === t)?.parentId;
  for (; r; ) {
    const s = e.find((o) => o.id === r);
    ((r = s?.parentId), s && (n = n.concat(s)));
  }
  return n;
}
function xn(e) {
  return `data-base-ui-${e}`;
}
let In = 0;
function kr(e, t = {}) {
  const { preventScroll: n = !1, sync: r = !1, shouldFocus: s } = t;
  cancelAnimationFrame(In);
  function o() {
    (s && !s()) || e?.focus({ preventScroll: n });
  }
  if (r) return (o(), os);
  const i = requestAnimationFrame(o);
  return (
    (In = i),
    () => {
      In === i && (cancelAnimationFrame(i), (In = 0));
    }
  );
}
const Ar = { inert: new WeakMap(), "aria-hidden": new WeakMap() },
  Xs = "data-base-ui-inert",
  zr = { inert: new WeakSet(), "aria-hidden": new WeakSet() };
let un = new WeakMap(),
  Or = 0;
function Gc(e) {
  return zr[e];
}
function Ei(e) {
  return e ? (rn(e) ? e.host : Ei(e.parentNode)) : null;
}
const jr = (e, t) =>
    t
      .map((n) => {
        if (e.contains(n)) return n;
        const r = Ei(n);
        return e.contains(r) ? r : null;
      })
      .filter((n) => n != null),
  zs = (e) => {
    const t = new Set();
    return (
      e.forEach((n) => {
        let r = n;
        for (; r && !t.has(r); ) (t.add(r), (r = r.parentNode));
      }),
      t
    );
  },
  qs = (e, t, n) => {
    const r = [],
      s = (o) => {
        !o ||
          n.has(o) ||
          Array.from(o.children).forEach((i) => {
            ze(i) !== "script" && (t.has(i) ? s(i) : r.push(i));
          });
      };
    return (s(e), r);
  };
function Uc(e, t, n, r, { mark: s = !0, markerIgnoreElements: o = [] }) {
  const i = r ? "inert" : n ? "aria-hidden" : null;
  let a = null,
    f = null;
  const u = jr(t, e),
    l = s ? jr(t, o) : [],
    d = new Set(l),
    p = s ? qs(t, zs(u), new Set(u)).filter((x) => !d.has(x)) : [],
    g = [],
    h = [];
  if (i) {
    const x = Ar[i],
      v = Gc(i);
    ((f = v), (a = x));
    const S = jr(t, Array.from(t.querySelectorAll("[aria-live]"))),
      b = u.concat(S);
    qs(t, zs(b), new Set(b)).forEach((w) => {
      const R = w.getAttribute(i),
        E = R !== null && R !== "false",
        T = (x.get(w) || 0) + 1;
      (x.set(w, T),
        g.push(w),
        T === 1 && E && v.add(w),
        E || w.setAttribute(i, i === "inert" ? "" : "true"));
    });
  }
  return (
    s &&
      p.forEach((x) => {
        const v = (un.get(x) || 0) + 1;
        (un.set(x, v), h.push(x), v === 1 && x.setAttribute(Xs, ""));
      }),
    (Or += 1),
    () => {
      (a &&
        g.forEach((x) => {
          const S = (a.get(x) || 0) - 1;
          (a.set(x, S),
            S || (!f?.has(x) && i && x.removeAttribute(i), f?.delete(x)));
        }),
        s &&
          h.forEach((x) => {
            const v = (un.get(x) || 0) - 1;
            (un.set(x, v), v || x.removeAttribute(Xs));
          }),
        (Or -= 1),
        Or ||
          ((Ar.inert = new WeakMap()),
          (Ar["aria-hidden"] = new WeakMap()),
          (zr.inert = new WeakSet()),
          (zr["aria-hidden"] = new WeakSet()),
          (un = new WeakMap())));
    }
  );
}
function Zs(e, t = {}) {
  const {
      ariaHidden: n = !1,
      inert: r = !1,
      mark: s = !0,
      markerIgnoreElements: o = [],
    } = t,
    i = Ie(e[0]).body;
  return Uc(e, i, n, r, { mark: s, markerIgnoreElements: o });
}
var zt = za();
let Qs = 0;
function Wc(e, t = "mui") {
  const [n, r] = m.useState(e),
    s = e || n;
  return (
    m.useEffect(() => {
      n == null && ((Qs += 1), r(`${t}-${Qs}`));
    }, [n, t]),
    s
  );
}
const Js = as.useId;
function sr(e, t) {
  if (Js !== void 0) {
    const n = Js();
    return e ?? (t ? `${t}-${n}` : n);
  }
  return Wc(e, t);
}
const Kc = parseInt(m.version, 10);
function fs(e) {
  return Kc >= e;
}
function eo(e) {
  if (!m.isValidElement(e)) return null;
  const t = e,
    n = t.props;
  return (fs(19) ? n?.ref : t.ref) ?? null;
}
function qr(e, t) {
  if (e && !t) return e;
  if (!e && t) return t;
  if (e || t) return { ...e, ...t };
}
function Vc(e, t) {
  const n = {};
  for (const r in e) {
    const s = e[r];
    if (t?.hasOwnProperty(r)) {
      const o = t[r](s);
      o != null && Object.assign(n, o);
      continue;
    }
    s === !0
      ? (n[`data-${r.toLowerCase()}`] = "")
      : s && (n[`data-${r.toLowerCase()}`] = s.toString());
  }
  return n;
}
function Yc(e, t) {
  return typeof e == "function" ? e(t) : e;
}
function Xc(e, t) {
  return typeof e == "function" ? e(t) : e;
}
const ps = {};
function Yt(e, t, n, r, s) {
  if (!n && !r && !e) return Yn(t);
  let o = Yn(e);
  return (t && (o = Dn(o, t)), n && (o = Dn(o, n)), r && (o = Dn(o, r)), o);
}
function zc(e) {
  if (e.length === 0) return ps;
  if (e.length === 1) return Yn(e[0]);
  let t = Yn(e[0]);
  for (let n = 1; n < e.length; n += 1) t = Dn(t, e[n]);
  return t;
}
function Yn(e) {
  return hs(e) ? { ...ki(e, ps) } : qc(e);
}
function Dn(e, t) {
  return hs(t) ? ki(t, e) : Zc(e, t);
}
function qc(e) {
  const t = { ...e };
  for (const n in t) {
    const r = t[n];
    Ri(n, r) && (t[n] = Ai(r));
  }
  return t;
}
function Zc(e, t) {
  if (!t) return e;
  for (const n in t) {
    const r = t[n];
    switch (n) {
      case "style": {
        e[n] = qr(e.style, r);
        break;
      }
      case "className": {
        e[n] = Oi(e.className, r);
        break;
      }
      default:
        Ri(n, r) ? (e[n] = Qc(e[n], r)) : (e[n] = r);
    }
  }
  return e;
}
function Ri(e, t) {
  const n = e.charCodeAt(0),
    r = e.charCodeAt(1),
    s = e.charCodeAt(2);
  return (
    n === 111 &&
    r === 110 &&
    s >= 65 &&
    s <= 90 &&
    (typeof t == "function" || typeof t > "u")
  );
}
function hs(e) {
  return typeof e == "function";
}
function ki(e, t) {
  return hs(e) ? e(t) : (e ?? ps);
}
function Qc(e, t) {
  return t
    ? e
      ? (...n) => {
          const r = n[0];
          if (ji(r)) {
            const o = r;
            Xn(o);
            const i = t(...n);
            return (o.baseUIHandlerPrevented || e?.(...n), i);
          }
          const s = t(...n);
          return (e?.(...n), s);
        }
      : Ai(t)
    : e;
}
function Ai(e) {
  return (
    e &&
    ((...t) => {
      const n = t[0];
      return (ji(n) && Xn(n), e(...t));
    })
  );
}
function Xn(e) {
  return (
    (e.preventBaseUIHandler = () => {
      e.baseUIHandlerPrevented = !0;
    }),
    e
  );
}
function Oi(e, t) {
  return t ? (e ? t + " " + e : t) : e;
}
function ji(e) {
  return e != null && typeof e == "object" && "nativeEvent" in e;
}
function Nt(e, t, n = {}) {
  const r = t.render,
    s = Jc(t, n);
  if (n.enabled === !1) return null;
  const o = n.state ?? Xe;
  return nu(e, r, s, o);
}
function Jc(e, t = {}) {
  const { className: n, style: r, render: s } = e,
    {
      state: o = Xe,
      ref: i,
      props: a,
      stateAttributesMapping: f,
      enabled: u = !0,
    } = t,
    l = u ? Yc(n, o) : void 0,
    d = u ? Xc(r, o) : void 0,
    p = u ? Vc(o, f) : Xe,
    g = u && a ? eu(a) : void 0,
    h = u ? (qr(p, g) ?? {}) : Xe;
  return (
    typeof document < "u" &&
      (u
        ? Array.isArray(i)
          ? (h.ref = gc([h.ref, eo(s), ...i]))
          : (h.ref = Gn(h.ref, eo(s), i))
        : Gn(null, null)),
    u
      ? (l !== void 0 && (h.className = Oi(h.className, l)),
        d !== void 0 && (h.style = qr(h.style, d)),
        h)
      : Xe
  );
}
function eu(e) {
  return Array.isArray(e) ? zc(e) : Yt(void 0, e);
}
const tu = Symbol.for("react.lazy");
function nu(e, t, n, r) {
  if (t) {
    if (typeof t == "function") return t(n, r);
    const s = Yt(n, t.props);
    s.ref = n.ref;
    let o = t;
    return (
      o?.$$typeof === tu && (o = m.Children.toArray(t)[0]),
      m.cloneElement(o, s)
    );
  }
  if (e && typeof e == "string") return ru(e, n);
  throw new Error(It(8));
}
function ru(e, t) {
  return e === "button"
    ? m.createElement("button", { type: "button", ...t, key: t.key })
    : e === "img"
      ? m.createElement("img", { alt: "", ...t, key: t.key })
      : m.createElement(e, t);
}
const su = { style: { transition: "none" } },
  ou = "data-base-ui-click-trigger",
  iu = { fallbackAxisSide: "end" },
  au = { clipPath: "inset(50%)", position: "fixed", top: 0, left: 0 },
  Ii = m.createContext(null),
  Ni = () => m.useContext(Ii),
  lu = xn("portal");
function Pi(e = {}) {
  const { ref: t, container: n, componentProps: r = Xe, elementProps: s } = e,
    o = sr(),
    a = Ni()?.portalNode,
    [f, u] = m.useState(null),
    [l, d] = m.useState(null),
    p = Te((v) => {
      v !== null && d(v);
    }),
    g = m.useRef(null);
  xe(() => {
    if (n === null) {
      g.current && ((g.current = null), d(null), u(null));
      return;
    }
    if (o == null) return;
    const v = (n && (ns(n) ? n : n.current)) ?? a ?? document.body;
    if (v == null) {
      g.current && ((g.current = null), d(null), u(null));
      return;
    }
    g.current !== v && ((g.current = v), d(null), u(v));
  }, [n, a, o]);
  const h = Nt("div", r, { ref: [t, p], props: [{ id: o, [lu]: "" }, s] });
  return {
    portalNode: l,
    portalSubtree: f && h ? zt.createPortal(h, f) : null,
  };
}
const cu = m.forwardRef(function (t, n) {
  const {
      render: r,
      className: s,
      style: o,
      children: i,
      container: a,
      renderGuards: f,
      ...u
    } = t,
    { portalNode: l, portalSubtree: d } = Pi({
      container: a,
      ref: n,
      componentProps: t,
      elementProps: u,
    }),
    p = m.useRef(null),
    g = m.useRef(null),
    h = m.useRef(null),
    x = m.useRef(null),
    [v, S] = m.useState(null),
    b = m.useRef(!1),
    C = v?.modal,
    w = v?.open,
    R = typeof f == "boolean" ? f : !!v && !v.modal && v.open && !!l;
  (m.useEffect(() => {
    if (!l || C) return;
    function T(O) {
      l &&
        O.relatedTarget &&
        pn(O) &&
        (O.type === "focusin"
          ? b.current && (Vs(l), (b.current = !1))
          : ($c(l), (b.current = !0)));
    }
    return yt(me(l, "focusin", T, !0), me(l, "focusout", T, !0));
  }, [l, C]),
    m.useEffect(() => {
      !l || w !== !1 || (Vs(l), (b.current = !1));
    }, [w, l]));
  const E = m.useMemo(
    () => ({
      beforeOutsideRef: p,
      afterOutsideRef: g,
      beforeInsideRef: h,
      afterInsideRef: x,
      portalNode: l,
      setFocusManagerState: S,
    }),
    [l],
  );
  return c.jsxs(m.Fragment, {
    children: [
      d,
      c.jsxs(Ii.Provider, {
        value: E,
        children: [
          R &&
            l &&
            c.jsx(Un, {
              "data-type": "outside",
              ref: p,
              onFocus: (T) => {
                if (pn(T, l)) h.current?.focus();
                else {
                  const O = v ? v.domReference : null;
                  Ti(O)?.focus();
                }
              },
            }),
          R && l && c.jsx("span", { "aria-owns": l.id, style: au }),
          l && zt.createPortal(i, l),
          R &&
            l &&
            c.jsx(Un, {
              "data-type": "outside",
              ref: g,
              onFocus: (T) => {
                if (pn(T, l)) x.current?.focus();
                else {
                  const O = v ? v.domReference : null;
                  (Ci(O)?.focus(),
                    v?.closeOnFocusOut &&
                      v?.onOpenChange(!1, Be(ai, T.nativeEvent)));
                }
              },
            }),
        ],
      }),
    ],
  });
});
function uu() {
  const e = new Map();
  return {
    emit(t, n) {
      e.get(t)?.forEach((r) => r(n));
    },
    on(t, n) {
      (e.has(t) || e.set(t, new Set()), e.get(t).add(n));
    },
    off(t, n) {
      e.get(t)?.delete(n);
    },
  };
}
const du = m.createContext(null),
  fu = m.createContext(null),
  ms = () => m.useContext(du)?.id || null,
  yn = (e) => {
    const t = m.useContext(fu);
    return e ?? t;
  };
function Et(e) {
  return e == null ? e : "current" in e ? e.current : e;
}
function pu(e, t) {
  const n = Ge(it(e));
  return e instanceof n.KeyboardEvent
    ? "keyboard"
    : e instanceof n.FocusEvent
      ? t || "keyboard"
      : "pointerType" in e
        ? e.pointerType || "keyboard"
        : "touches" in e
          ? "touch"
          : e instanceof n.MouseEvent
            ? t || (e.detail === 0 ? "keyboard" : "mouse")
            : "";
}
const to = 20;
let Dt = [];
function gs() {
  Dt = Dt.filter((e) => e.deref()?.isConnected);
}
function hu(e) {
  (gs(),
    e &&
      ze(e) !== "body" &&
      (Dt.push(new WeakRef(e)), Dt.length > to && (Dt = Dt.slice(-to))));
}
function Ir() {
  return (gs(), Dt[Dt.length - 1]?.deref());
}
function mu(e) {
  return e ? (ds(e) ? e : rr(e)[0] || e) : null;
}
function no(e, t) {
  if (
    (e.hasAttribute("tabindex") && !e.hasAttribute("data-tabindex")) ||
    (!t.current.includes("floating") &&
      !e.getAttribute("role")?.includes("dialog"))
  )
    return;
  const r = Si(e).filter((o) => {
      const i = o.getAttribute("data-tabindex") || "";
      return ds(o) || (o.hasAttribute("data-tabindex") && !i.startsWith("-"));
    }),
    s = e.getAttribute("tabindex");
  t.current.includes("floating") || r.length === 0
    ? s !== "0" && e.setAttribute("tabindex", "0")
    : (s !== "-1" ||
        (e.hasAttribute("data-tabindex") &&
          e.getAttribute("data-tabindex") !== "-1")) &&
      (e.setAttribute("tabindex", "-1"), e.setAttribute("data-tabindex", "-1"));
}
function gu(e) {
  const {
      context: t,
      children: n,
      disabled: r = !1,
      initialFocus: s = !0,
      returnFocus: o = !0,
      restoreFocus: i = !1,
      modal: a = !0,
      closeOnFocusOut: f = !0,
      openInteractionType: u = "",
      nextFocusableElement: l,
      previousFocusableElement: d,
      beforeContentFocusGuardRef: p,
      externalTree: g,
      getInsideElements: h,
    } = e,
    x = "rootStore" in t ? t.rootStore : t,
    v = x.useState("open"),
    S = x.useState("domReferenceElement"),
    b = x.useState("floatingElement"),
    { events: C, dataRef: w } = x.context,
    R = Te(() => w.current.floatingContext?.nodeId),
    E = s === !1,
    T = $s(S) && E,
    O = m.useRef(["content"]),
    A = et(s),
    j = et(o),
    $ = et(u),
    P = yn(g),
    I = Ni(),
    L = m.useRef(!1),
    k = m.useRef(!1),
    M = m.useRef(!1),
    H = m.useRef(null),
    N = m.useRef(""),
    D = m.useRef(""),
    U = m.useRef(null),
    Q = m.useRef(null),
    ve = Gn(U, p, I?.beforeInsideRef),
    Y = Gn(Q, I?.afterInsideRef),
    J = Lt(),
    ce = Lt(),
    z = fi(),
    ue = I != null,
    X = Gs(b),
    te = Te((B = X) => (B ? rr(B) : [])),
    ye = Te(() => h?.().filter((B) => B != null) ?? []);
  (m.useEffect(() => {
    if (r || !a) return;
    function B(ne) {
      ne.key === "Tab" && ie(X, ft(Ie(X))) && te().length === 0 && !T && Ql(ne);
    }
    const G = Ie(X);
    return me(G, "keydown", B);
  }, [r, X, a, T, te]),
    m.useEffect(() => {
      if (r || !v) return;
      const B = Ie(X);
      function G() {
        M.current = !1;
      }
      function ne(se) {
        const q = it(se),
          be = ye(),
          ee =
            ie(b, q) ||
            ie(S, q) ||
            ie(I?.portalNode, q) ||
            be.some((Ne) => Ne === q || ie(Ne, q));
        ((M.current = !ee),
          (D.current = se.pointerType || "keyboard"),
          q?.closest(`[${ou}]`) && (k.current = !0));
      }
      function de() {
        D.current = "keyboard";
      }
      return yt(
        me(B, "pointerdown", ne, !0),
        me(B, "pointerup", G, !0),
        me(B, "pointercancel", G, !0),
        me(B, "keydown", de, !0),
      );
    }, [r, b, S, X, v, I, ye]),
    m.useEffect(() => {
      if (r || !f) return;
      const B = Ie(X);
      function G() {
        ((k.current = !0),
          ce.start(0, () => {
            k.current = !1;
          }));
      }
      function ne(be) {
        const ee = it(be);
        ds(ee) && (H.current = ee);
      }
      function de(be) {
        const ee = be.relatedTarget,
          Ne = be.currentTarget,
          Me = it(be);
        queueMicrotask(() => {
          const _e = R(),
            Re = x.context.triggerElements,
            Ve = ye(),
            F =
              ee?.hasAttribute(xn("focus-guard")) &&
              [
                U.current,
                Q.current,
                I?.beforeInsideRef.current,
                I?.afterInsideRef.current,
                I?.beforeOutsideRef.current,
                I?.afterOutsideRef.current,
                Et(d),
                Et(l),
              ].includes(ee),
            K = !(
              ie(S, ee) ||
              ie(b, ee) ||
              ie(ee, b) ||
              ie(I?.portalNode, ee) ||
              Ve.some((oe) => oe === ee || ie(oe, ee)) ||
              (ee != null && Re.hasElement(ee)) ||
              Re.hasMatchingElement((oe) => ie(oe, ee)) ||
              F ||
              (P &&
                (Ft(P.nodesRef.current, _e).find(
                  (oe) =>
                    ie(oe.context?.elements.floating, ee) ||
                    ie(oe.context?.elements.domReference, ee),
                ) ||
                  Ys(P.nodesRef.current, _e).find(
                    (oe) =>
                      [
                        oe.context?.elements.floating,
                        Gs(oe.context?.elements.floating),
                      ].includes(ee) ||
                      oe.context?.elements.domReference === ee,
                  )))
            );
          if (
            (Ne === S && X && no(X, O),
            i && Ne !== S && !hi(Me) && ft(B) === B.body)
          ) {
            if (Le(X) && (X.focus(), i === "popup")) {
              z.request(() => {
                X.focus();
              });
              return;
            }
            const oe = te(),
              je = H.current,
              Fe =
                (je && oe.includes(je) ? je : null) || oe[oe.length - 1] || X;
            Le(Fe) && Fe.focus();
          }
          if (w.current.insideReactTree) {
            w.current.insideReactTree = !1;
            return;
          }
          (T || !a) &&
            ee &&
            K &&
            !k.current &&
            (T || ee !== Ir()) &&
            ((L.current = !0), x.setOpen(!1, Be(ai, be)));
        });
      }
      function se() {
        M.current ||
          ((w.current.insideReactTree = !0),
          J.start(0, () => {
            w.current.insideReactTree = !1;
          }));
      }
      const q = Le(S) ? S : null;
      if (!(!b && !q))
        return yt(
          q && me(q, "focusout", de),
          q && me(q, "pointerdown", G),
          b && me(b, "focusin", ne),
          b && me(b, "focusout", de),
          b && I && me(b, "focusout", se, !0),
        );
    }, [r, S, b, X, a, P, I, x, f, i, te, T, R, O, w, J, ce, z, l, d, ye]),
    m.useEffect(() => {
      if (r || !b || !v) return;
      const B = Array.from(
          I?.portalNode?.querySelectorAll(`[${xn("portal")}]`) || [],
        ),
        ne = (P ? Ys(P.nodesRef.current, R()) : []).find((Ne) =>
          $s(Ne.context?.elements.domReference || null),
        )?.context?.elements.domReference,
        se = [
          ...[
            b,
            ...B,
            U.current,
            Q.current,
            I?.beforeOutsideRef.current,
            I?.afterOutsideRef.current,
            ...ye(),
          ],
          ne,
          Et(d),
          Et(l),
          T ? S : null,
        ].filter((Ne) => Ne != null),
        q = Zs(se, { ariaHidden: a || T, mark: !1 }),
        be = [b, ...B].filter((Ne) => Ne != null),
        ee = Zs(be);
      return () => {
        (ee(), q());
      };
    }, [v, r, S, b, a, I, T, P, R, l, d, ye]),
    xe(() => {
      if (!v || r || !Le(X)) return;
      const B = Ie(X),
        G = ft(B);
      queueMicrotask(() => {
        const ne = A.current,
          de = typeof ne == "function" ? ne($.current || "") : ne;
        if (de === void 0 || de === !1 || ie(X, G)) return;
        let q = null;
        const be = () => (q == null && (q = te(X)), q[0] || X);
        let ee;
        (de === !0 || de === null ? (ee = be()) : (ee = Et(de)),
          (ee = ee || be()));
        const Ne = ie(X, ft(B));
        kr(ee, {
          preventScroll: ee === X,
          shouldFocus() {
            if (Ne) return !0;
            const Me = ft(B);
            return !(Me !== ee && ie(X, Me));
          },
        });
      });
    }, [r, v, X, te, A, $]),
    xe(() => {
      if (r || !X) return;
      const B = Ie(X),
        G = ft(B);
      hu(G);
      function ne(se) {
        if (
          (se.open || (N.current = pu(se.nativeEvent, D.current)),
          se.reason === Ze &&
            se.nativeEvent.type === "mouseleave" &&
            (L.current = !0),
          se.reason === ii)
        )
          if (se.nested) L.current = !1;
          else if (ec(se.nativeEvent) || tc(se.nativeEvent)) L.current = !1;
          else {
            let q = !1;
            (Ie(X)
              .createElement("div")
              .focus({
                get preventScroll() {
                  return ((q = !0), !1);
                },
              }),
              q ? (L.current = !1) : (L.current = !0));
          }
      }
      C.on("openchange", ne);
      function de() {
        const se = j.current;
        let q = typeof se == "function" ? se(N.current) : se;
        if (q === void 0 || q === !1) return null;
        if ((q === null && (q = !0), typeof q == "boolean"))
          return S?.isConnected ? S : Ir() || null;
        const be = S?.isConnected ? S : Ir();
        return Et(q) || be || null;
      }
      return () => {
        C.off("openchange", ne);
        const se = ft(B),
          q = ye(),
          be =
            ie(b, se) ||
            q.some((Me) => Me === se || ie(Me, se)) ||
            (P &&
              Ft(P.nodesRef.current, R(), !1).some((Me) =>
                ie(Me.context?.elements.floating, se),
              )),
          ee = j.current,
          Ne = de();
        queueMicrotask(() => {
          const Me = mu(Ne),
            _e = typeof ee != "boolean";
          (ee &&
            !L.current &&
            Le(Me) &&
            (!(!_e && Me !== se && se !== B.body) || be) &&
            Me.focus({ preventScroll: !0 }),
            (L.current = !1));
        });
      };
    }, [r, b, X, j, C, P, S, R, ye]),
    xe(() => {
      if (!Jo || v || !b) return;
      const B = ft(Ie(b));
      !Le(B) || !ss(B) || (ie(b, B) && B.blur());
    }, [v, b]),
    xe(() => {
      if (!(r || !I))
        return (
          I.setFocusManagerState({
            modal: a,
            closeOnFocusOut: f,
            open: v,
            onOpenChange: x.setOpen,
            domReference: S,
          }),
          () => {
            I.setFocusManagerState(null);
          }
        );
    }, [r, I, a, v, x, f, S]),
    xe(() => {
      if (!(r || !X))
        return (
          no(X, O),
          () => {
            queueMicrotask(gs);
          }
        );
    }, [r, X, O]));
  const W = !r && (a ? !T : !0) && (ue || a);
  return c.jsxs(m.Fragment, {
    children: [
      W &&
        c.jsx(Un, {
          "data-type": "inside",
          ref: ve,
          onFocus: (B) => {
            if (a) {
              const G = te();
              kr(G[G.length - 1]);
            } else
              I?.portalNode &&
                ((L.current = !1),
                pn(B, I.portalNode)
                  ? Ci(S)?.focus()
                  : Et(d ?? I.beforeOutsideRef)?.focus());
          },
        }),
      n,
      W &&
        c.jsx(Un, {
          "data-type": "inside",
          ref: Y,
          onFocus: (B) => {
            a
              ? kr(te()[0])
              : I?.portalNode &&
                (f && (L.current = !0),
                pn(B, I.portalNode)
                  ? Ti(S)?.focus()
                  : Et(l ?? I.afterOutsideRef)?.focus());
          },
        }),
    ],
  });
}
function xu(e, t) {
  let n = null,
    r = null,
    s = !1;
  return {
    contextElement: e || void 0,
    getBoundingClientRect() {
      const o = e?.getBoundingClientRect() || {
          width: 0,
          height: 0,
          x: 0,
          y: 0,
        },
        i = t.axis === "x" || t.axis === "both",
        a = t.axis === "y" || t.axis === "both",
        f =
          ["mouseenter", "mousemove"].includes(
            t.dataRef.current.openEvent?.type || "",
          ) && t.pointerType !== "touch";
      let u = o.width,
        l = o.height,
        d = o.x,
        p = o.y;
      return (
        n == null && t.x && i && (n = o.x - t.x),
        r == null && t.y && a && (r = o.y - t.y),
        (d -= n || 0),
        (p -= r || 0),
        (u = 0),
        (l = 0),
        !s || f
          ? ((u = t.axis === "y" ? o.width : 0),
            (l = t.axis === "x" ? o.height : 0),
            (d = i && t.x != null ? t.x : d),
            (p = a && t.y != null ? t.y : p))
          : s &&
            !f &&
            ((l = t.axis === "x" ? o.height : l),
            (u = t.axis === "y" ? o.width : u)),
        (s = !0),
        {
          width: u,
          height: l,
          x: d,
          y: p,
          top: p,
          right: d + u,
          bottom: p + l,
          left: d,
        }
      );
    },
  };
}
function ro(e) {
  return e != null && e.clientX != null;
}
function bu(e, t = {}) {
  const { enabled: n = !0, axis: r = "both" } = t,
    s = "rootStore" in e ? e.rootStore : e,
    o = s.useState("open"),
    i = s.useState("floatingElement"),
    a = s.useState("domReferenceElement"),
    f = s.context.dataRef,
    u = m.useRef(!1),
    l = m.useRef(null),
    [d, p] = m.useState(),
    [g, h] = m.useState([]),
    x = Te((w) => {
      s.set("positionReference", w);
    }),
    v = Te((w, R, E) => {
      u.current ||
        (f.current.openEvent && !ro(f.current.openEvent)) ||
        s.set(
          "positionReference",
          xu(E ?? a, { x: w, y: R, axis: r, dataRef: f, pointerType: d }),
        );
    }),
    S = Te((w) => {
      o
        ? l.current || (v(w.clientX, w.clientY, w.currentTarget), h([]))
        : v(w.clientX, w.clientY, w.currentTarget);
    }),
    b = mn(d) ? i : o;
  (m.useEffect(() => {
    if (!n) {
      x(a);
      return;
    }
    if (!b) return;
    function w() {
      (l.current?.(), (l.current = null));
    }
    const R = Ge(i);
    function E(T) {
      const O = it(T);
      ie(i, O) ? w() : v(T.clientX, T.clientY);
    }
    return (
      !f.current.openEvent || ro(f.current.openEvent)
        ? (l.current = me(R, "mousemove", E))
        : x(a),
      w
    );
  }, [b, n, i, f, a, s, v, x, g]),
    m.useEffect(
      () => () => {
        s.set("positionReference", null);
      },
      [s],
    ),
    m.useEffect(() => {
      n && !i && (u.current = !1);
    }, [n, i]),
    m.useEffect(() => {
      !n && o && (u.current = !0);
    }, [n, o]));
  const C = m.useMemo(() => {
    function w(R) {
      p(R.pointerType);
    }
    return {
      onPointerDown: w,
      onPointerEnter: w,
      onMouseMove: S,
      onMouseEnter: S,
    };
  }, [S]);
  return m.useMemo(() => (n ? { reference: C, trigger: C } : {}), [n, C]);
}
const vu = { intentional: "onClick", sloppy: "onPointerDown" };
function yu() {
  return !1;
}
function Su(e) {
  return {
    escapeKey: typeof e == "boolean" ? e : (e?.escapeKey ?? !1),
    outsidePress: typeof e == "boolean" ? e : (e?.outsidePress ?? !0),
  };
}
function Bi(e, t = {}) {
  const {
      enabled: n = !0,
      escapeKey: r = !0,
      outsidePress: s = !0,
      outsidePressEvent: o = "sloppy",
      referencePress: i = yu,
      referencePressEvent: a = "sloppy",
      bubbles: f,
      externalTree: u,
    } = t,
    l = "rootStore" in e ? e.rootStore : e,
    d = l.useState("open"),
    p = l.useState("floatingElement"),
    { dataRef: g } = l.context,
    h = yn(u),
    x = Te(typeof s == "function" ? s : () => !1),
    v = typeof s == "function" ? x : s,
    S = v !== !1,
    b = Te(() => o),
    { escapeKey: C, outsidePress: w } = Su(f),
    R = m.useRef(!1),
    E = m.useRef(!1),
    T = m.useRef(!1),
    O = m.useRef(!1),
    A = m.useRef(""),
    j = m.useRef(null),
    $ = Lt(),
    P = Lt(),
    I = Te(() => {
      (P.clear(), (g.current.insideReactTree = !1));
    }),
    L = Te((Y) => {
      const J = g.current.floatingContext?.nodeId;
      return (h ? Ft(h.nodesRef.current, J) : []).some(
        (z) => z.context?.open && !z.context.dataRef.current[Y],
      );
    }),
    k = Te(
      (Y) =>
        Tr(Y, l.select("floatingElement")) ||
        Tr(Y, l.select("domReferenceElement")),
    ),
    M = Te((Y) => {
      i() && l.setOpen(!1, Be($n, Y.nativeEvent));
    }),
    H = Te((Y) => {
      if (
        !d ||
        !n ||
        !r ||
        Y.key !== "Escape" ||
        O.current ||
        (!C && L("__escapeKeyBubbles"))
      )
        return;
      const J = Jl(Y) ? Y.nativeEvent : Y,
        ce = Be(is, J);
      (l.setOpen(!1, ce),
        ce.isCanceled || Y.preventDefault(),
        !C && !ce.isPropagationAllowed && Y.stopPropagation());
    }),
    N = Te(() => {
      ((g.current.insideReactTree = !0), P.start(0, I));
    }),
    D = Te((Y) => {
      if (!d || !n || Y.button !== 0) return;
      const J = it(Y.nativeEvent);
      ie(l.select("floatingElement"), J) &&
        (R.current || ((R.current = !0), (E.current = !1)));
    }),
    U = Te((Y) => {
      !d ||
        !n ||
        ((Y.defaultPrevented || Y.nativeEvent.defaultPrevented) &&
          R.current &&
          (E.current = !0));
    });
  (m.useEffect(() => {
    if (!d || !n) return;
    ((g.current.__escapeKeyBubbles = C), (g.current.__outsidePressBubbles = w));
    const Y = new pt(),
      J = new pt();
    function ce() {
      (Y.clear(), (O.current = !0));
    }
    function z() {
      Y.start(tr() ? 5 : 0, () => {
        O.current = !1;
      });
    }
    function ue() {
      ((T.current = !0),
        J.start(0, () => {
          T.current = !1;
        }));
    }
    function X() {
      ((R.current = !1), (E.current = !1));
    }
    function te() {
      const F = A.current,
        K = F === "pen" || !F ? "mouse" : F,
        oe = b(),
        je = typeof oe == "function" ? oe() : oe;
      return typeof je == "string" ? je : je[K];
    }
    function ye(F) {
      const K = te();
      return (
        (K === "intentional" && F.type !== "click") ||
        (K === "sloppy" && F.type === "click")
      );
    }
    function W(F) {
      const K = g.current.floatingContext?.nodeId,
        oe =
          h &&
          Ft(h.nodesRef.current, K).some((je) =>
            Tr(F, je.context?.elements.floating),
          );
      return k(F) || oe;
    }
    function B(F) {
      if (ye(F)) {
        (F.type !== "click" && !k(F) && (J.clear(), (T.current = !1)), I());
        return;
      }
      if (g.current.insideReactTree) {
        I();
        return;
      }
      const K = it(F),
        oe = `[${xn("inert")}]`,
        je = he(K) ? K.getRootNode() : null,
        Fe = Array.from(
          (rn(je) ? je : Ie(l.select("floatingElement"))).querySelectorAll(oe),
        ),
        ct = l.context.triggerElements;
      if (K && (ct.hasElement(K) || ct.hasMatchingElement((fe) => ie(fe, K))))
        return;
      let le = he(K) ? K : null;
      for (; le && !kt(le); ) {
        const fe = At(le);
        if (kt(fe) || !he(fe)) break;
        le = fe;
      }
      if (
        !(
          Fe.length &&
          he(K) &&
          !ac(K) &&
          !ie(K, l.select("floatingElement")) &&
          Fe.every((fe) => !ie(le, fe))
        )
      ) {
        if (Le(K) && !("touches" in F)) {
          const fe = kt(K),
            we = nt(K),
            $e = /auto|scroll/,
            Ue = fe || $e.test(we.overflowX),
            We = fe || $e.test(we.overflowY),
            Ke = Ue && K.clientWidth > 0 && K.scrollWidth > K.clientWidth,
            Ye = We && K.clientHeight > 0 && K.scrollHeight > K.clientHeight,
            pe = we.direction === "rtl",
            Pe =
              Ye &&
              (pe
                ? F.offsetX <= K.offsetWidth - K.clientWidth
                : F.offsetX > K.clientWidth),
            Se = Ke && F.offsetY > K.clientHeight;
          if (Pe || Se) return;
        }
        if (!W(F)) {
          if (te() === "intentional" && T.current) {
            (J.clear(), (T.current = !1));
            return;
          }
          (typeof v == "function" && !v(F)) ||
            L("__outsidePressBubbles") ||
            (l.setOpen(!1, Be(ii, F)), I());
        }
      }
    }
    function G(F) {
      te() !== "sloppy" ||
        F.pointerType === "touch" ||
        !l.select("open") ||
        !n ||
        k(F) ||
        B(F);
    }
    function ne(F) {
      if (te() !== "sloppy" || !l.select("open") || !n || k(F)) return;
      const K = F.touches[0];
      K &&
        ((j.current = {
          startTime: Date.now(),
          startX: K.clientX,
          startY: K.clientY,
          dismissOnTouchEnd: !1,
          dismissOnMouseDown: !0,
        }),
        $.start(1e3, () => {
          j.current &&
            ((j.current.dismissOnTouchEnd = !1),
            (j.current.dismissOnMouseDown = !1));
        }));
    }
    function de(F, K) {
      const oe = it(F);
      if (!oe) return;
      const je = me(oe, F.type, () => {
        (K(F), je());
      });
    }
    function se(F) {
      ((A.current = "touch"), de(F, ne));
    }
    function q(F) {
      ($.clear(),
        F.type === "pointerdown" && (A.current = F.pointerType),
        !(
          F.type === "mousedown" &&
          j.current &&
          !j.current.dismissOnMouseDown
        ) &&
          de(F, (K) => {
            K.type === "pointerdown" ? G(K) : B(K);
          }));
    }
    function be(F) {
      if (!R.current) return;
      const K = E.current;
      if ((X(), te() === "intentional")) {
        if (F.type === "pointercancel") {
          K && ue();
          return;
        }
        if (!W(F)) {
          if (K) {
            ue();
            return;
          }
          (typeof v == "function" && !v(F)) ||
            (J.clear(), (T.current = !0), I());
        }
      }
    }
    function ee(F) {
      if (te() !== "sloppy" || !j.current || k(F)) return;
      const K = F.touches[0];
      if (!K) return;
      const oe = Math.abs(K.clientX - j.current.startX),
        je = Math.abs(K.clientY - j.current.startY),
        Fe = Math.sqrt(oe * oe + je * je);
      (Fe > 5 && (j.current.dismissOnTouchEnd = !0),
        Fe > 10 && (B(F), $.clear(), (j.current = null)));
    }
    function Ne(F) {
      de(F, ee);
    }
    function Me(F) {
      te() !== "sloppy" ||
        !j.current ||
        k(F) ||
        (j.current.dismissOnTouchEnd && B(F), $.clear(), (j.current = null));
    }
    function _e(F) {
      de(F, Me);
    }
    const Re = Ie(p),
      Ve = yt(
        r &&
          yt(
            me(Re, "keydown", H),
            me(Re, "compositionstart", ce),
            me(Re, "compositionend", z),
          ),
        S &&
          yt(
            me(Re, "click", q, !0),
            me(Re, "pointerdown", q, !0),
            me(Re, "pointerup", be, !0),
            me(Re, "pointercancel", be, !0),
            me(Re, "mousedown", q, !0),
            me(Re, "mouseup", be, !0),
            me(Re, "touchstart", se, !0),
            me(Re, "touchmove", Ne, !0),
            me(Re, "touchend", _e, !0),
          ),
      );
    return () => {
      (Ve(), Y.clear(), J.clear(), X(), (T.current = !1));
    };
  }, [g, p, r, S, v, d, n, C, w, H, I, b, L, k, h, l, $]),
    m.useEffect(I, [v, I]));
  const Q = m.useMemo(
      () => ({
        onKeyDown: H,
        [vu[a]]: M,
        ...(a !== "intentional" && { onClick: M }),
      }),
      [H, M, a],
    ),
    ve = m.useMemo(
      () => ({
        onKeyDown: H,
        onPointerDown: U,
        onMouseDown: U,
        onClickCapture: N,
        onMouseDownCapture(Y) {
          (N(), D(Y));
        },
        onPointerDownCapture(Y) {
          (N(), D(Y));
        },
        onMouseUpCapture: N,
        onTouchEndCapture: N,
        onTouchMoveCapture: N,
      }),
      [H, N, D, U],
    );
  return m.useMemo(
    () => (n ? { reference: Q, floating: ve, trigger: Q } : {}),
    [n, Q, ve],
  );
}
function so(e, t, n) {
  let { reference: r, floating: s } = e;
  const o = lt(t),
    i = us(t),
    a = cs(i),
    f = tt(t),
    u = o === "y",
    l = r.x + r.width / 2 - s.width / 2,
    d = r.y + r.height / 2 - s.height / 2,
    p = r[a] / 2 - s[a] / 2;
  let g;
  switch (f) {
    case "top":
      g = { x: l, y: r.y - s.height };
      break;
    case "bottom":
      g = { x: l, y: r.y + r.height };
      break;
    case "right":
      g = { x: r.x + r.width, y: d };
      break;
    case "left":
      g = { x: r.x - s.width, y: d };
      break;
    default:
      g = { x: r.x, y: r.y };
  }
  switch (_t(t)) {
    case "start":
      g[i] -= p * (n && u ? -1 : 1);
      break;
    case "end":
      g[i] += p * (n && u ? -1 : 1);
      break;
  }
  return g;
}
async function wu(e, t) {
  var n;
  t === void 0 && (t = {});
  const { x: r, y: s, platform: o, rects: i, elements: a, strategy: f } = e,
    {
      boundary: u = "clippingAncestors",
      rootBoundary: l = "viewport",
      elementContext: d = "floating",
      altBoundary: p = !1,
      padding: g = 0,
    } = Ot(t, e),
    h = pi(g),
    v = a[p ? (d === "floating" ? "reference" : "floating") : d],
    S = Vn(
      await o.getClippingRect({
        element:
          (n = await (o.isElement == null ? void 0 : o.isElement(v))) == null ||
          n
            ? v
            : v.contextElement ||
              (await (o.getDocumentElement == null
                ? void 0
                : o.getDocumentElement(a.floating))),
        boundary: u,
        rootBoundary: l,
        strategy: f,
      }),
    ),
    b =
      d === "floating"
        ? { x: r, y: s, width: i.floating.width, height: i.floating.height }
        : i.reference,
    C = await (o.getOffsetParent == null
      ? void 0
      : o.getOffsetParent(a.floating)),
    w = (await (o.isElement == null ? void 0 : o.isElement(C)))
      ? (await (o.getScale == null ? void 0 : o.getScale(C))) || { x: 1, y: 1 }
      : { x: 1, y: 1 },
    R = Vn(
      o.convertOffsetParentRelativeRectToViewportRelativeRect
        ? await o.convertOffsetParentRelativeRectToViewportRelativeRect({
            elements: a,
            rect: b,
            offsetParent: C,
            strategy: f,
          })
        : b,
    );
  return {
    top: (S.top - R.top + h.top) / w.y,
    bottom: (R.bottom - S.bottom + h.bottom) / w.y,
    left: (S.left - R.left + h.left) / w.x,
    right: (R.right - S.right + h.right) / w.x,
  };
}
const Cu = 50,
  Tu = async (e, t, n) => {
    const {
        placement: r = "bottom",
        strategy: s = "absolute",
        middleware: o = [],
        platform: i,
      } = n,
      a = i.detectOverflow ? i : { ...i, detectOverflow: wu },
      f = await (i.isRTL == null ? void 0 : i.isRTL(t));
    let u = await i.getElementRects({ reference: e, floating: t, strategy: s }),
      { x: l, y: d } = so(u, r, f),
      p = r,
      g = 0;
    const h = {};
    for (let x = 0; x < o.length; x++) {
      const v = o[x];
      if (!v) continue;
      const { name: S, fn: b } = v,
        {
          x: C,
          y: w,
          data: R,
          reset: E,
        } = await b({
          x: l,
          y: d,
          initialPlacement: r,
          placement: p,
          strategy: s,
          middlewareData: h,
          rects: u,
          platform: a,
          elements: { reference: e, floating: t },
        });
      ((l = C ?? l),
        (d = w ?? d),
        (h[S] = { ...h[S], ...R }),
        E &&
          g < Cu &&
          (g++,
          typeof E == "object" &&
            (E.placement && (p = E.placement),
            E.rects &&
              (u =
                E.rects === !0
                  ? await i.getElementRects({
                      reference: e,
                      floating: t,
                      strategy: s,
                    })
                  : E.rects),
            ({ x: l, y: d } = so(u, p, f))),
          (x = -1)));
    }
    return { x: l, y: d, placement: p, strategy: s, middlewareData: h };
  },
  Eu = function (e) {
    return (
      e === void 0 && (e = {}),
      {
        name: "flip",
        options: e,
        async fn(t) {
          var n, r;
          const {
              placement: s,
              middlewareData: o,
              rects: i,
              initialPlacement: a,
              platform: f,
              elements: u,
            } = t,
            {
              mainAxis: l = !0,
              crossAxis: d = !0,
              fallbackPlacements: p,
              fallbackStrategy: g = "bestFit",
              fallbackAxisSideDirection: h = "none",
              flipAlignment: x = !0,
              ...v
            } = Ot(e, t);
          if ((n = o.arrow) != null && n.alignmentOffset) return {};
          const S = tt(s),
            b = lt(a),
            C = tt(a) === a,
            w = await (f.isRTL == null ? void 0 : f.isRTL(u.floating)),
            R = p || (C || !x ? [Kn(a)] : Oc(a)),
            E = h !== "none";
          !p && E && R.push(...Pc(a, x, h, w));
          const T = [a, ...R],
            O = await f.detectOverflow(t, v),
            A = [];
          let j = ((r = o.flip) == null ? void 0 : r.overflows) || [];
          if ((l && A.push(O[S]), d)) {
            const L = Ac(s, i, w);
            A.push(O[L[0]], O[L[1]]);
          }
          if (
            ((j = [...j, { placement: s, overflows: A }]),
            !A.every((L) => L <= 0))
          ) {
            var $, P;
            const L = ((($ = o.flip) == null ? void 0 : $.index) || 0) + 1,
              k = T[L];
            if (
              k &&
              (!(d === "alignment" ? b !== lt(k) : !1) ||
                j.every((N) =>
                  lt(N.placement) === b ? N.overflows[0] > 0 : !0,
                ))
            )
              return {
                data: { index: L, overflows: j },
                reset: { placement: k },
              };
            let M =
              (P = j
                .filter((H) => H.overflows[0] <= 0)
                .sort((H, N) => H.overflows[1] - N.overflows[1])[0]) == null
                ? void 0
                : P.placement;
            if (!M)
              switch (g) {
                case "bestFit": {
                  var I;
                  const H =
                    (I = j
                      .filter((N) => {
                        if (E) {
                          const D = lt(N.placement);
                          return D === b || D === "y";
                        }
                        return !0;
                      })
                      .map((N) => [
                        N.placement,
                        N.overflows
                          .filter((D) => D > 0)
                          .reduce((D, U) => D + U, 0),
                      ])
                      .sort((N, D) => N[1] - D[1])[0]) == null
                      ? void 0
                      : I[0];
                  H && (M = H);
                  break;
                }
                case "initialPlacement":
                  M = a;
                  break;
              }
            if (s !== M) return { reset: { placement: M } };
          }
          return {};
        },
      }
    );
  };
function oo(e, t) {
  return {
    top: e.top - t.height,
    right: e.right - t.width,
    bottom: e.bottom - t.height,
    left: e.left - t.width,
  };
}
function io(e) {
  return Rc.some((t) => e[t] >= 0);
}
const Ru = function (e) {
    return (
      e === void 0 && (e = {}),
      {
        name: "hide",
        options: e,
        async fn(t) {
          const { rects: n, platform: r } = t,
            { strategy: s = "referenceHidden", ...o } = Ot(e, t);
          switch (s) {
            case "referenceHidden": {
              const i = await r.detectOverflow(t, {
                  ...o,
                  elementContext: "reference",
                }),
                a = oo(i, n.reference);
              return {
                data: { referenceHiddenOffsets: a, referenceHidden: io(a) },
              };
            }
            case "escaped": {
              const i = await r.detectOverflow(t, { ...o, altBoundary: !0 }),
                a = oo(i, n.floating);
              return { data: { escapedOffsets: a, escaped: io(a) } };
            }
            default:
              return {};
          }
        },
      }
    );
  },
  Mi = new Set(["left", "top"]);
async function ku(e, t) {
  const { placement: n, platform: r, elements: s } = e,
    o = await (r.isRTL == null ? void 0 : r.isRTL(s.floating)),
    i = tt(n),
    a = _t(n),
    f = lt(n) === "y",
    u = Mi.has(i) ? -1 : 1,
    l = o && f ? -1 : 1,
    d = Ot(t, e);
  let {
    mainAxis: p,
    crossAxis: g,
    alignmentAxis: h,
  } = typeof d == "number"
    ? { mainAxis: d, crossAxis: 0, alignmentAxis: null }
    : {
        mainAxis: d.mainAxis || 0,
        crossAxis: d.crossAxis || 0,
        alignmentAxis: d.alignmentAxis,
      };
  return (
    a && typeof h == "number" && (g = a === "end" ? h * -1 : h),
    f ? { x: g * l, y: p * u } : { x: p * u, y: g * l }
  );
}
const Au = function (e) {
    return (
      e === void 0 && (e = 0),
      {
        name: "offset",
        options: e,
        async fn(t) {
          var n, r;
          const { x: s, y: o, placement: i, middlewareData: a } = t,
            f = await ku(t, e);
          return i === ((n = a.offset) == null ? void 0 : n.placement) &&
            (r = a.arrow) != null &&
            r.alignmentOffset
            ? {}
            : { x: s + f.x, y: o + f.y, data: { ...f, placement: i } };
        },
      }
    );
  },
  Ou = function (e) {
    return (
      e === void 0 && (e = {}),
      {
        name: "shift",
        options: e,
        async fn(t) {
          const { x: n, y: r, placement: s, platform: o } = t,
            {
              mainAxis: i = !0,
              crossAxis: a = !1,
              limiter: f = {
                fn: (S) => {
                  let { x: b, y: C } = S;
                  return { x: b, y: C };
                },
              },
              ...u
            } = Ot(e, t),
            l = { x: n, y: r },
            d = await o.detectOverflow(t, u),
            p = lt(tt(s)),
            g = ls(p);
          let h = l[g],
            x = l[p];
          if (i) {
            const S = g === "y" ? "top" : "left",
              b = g === "y" ? "bottom" : "right",
              C = h + d[S],
              w = h - d[b];
            h = Vr(C, h, w);
          }
          if (a) {
            const S = p === "y" ? "top" : "left",
              b = p === "y" ? "bottom" : "right",
              C = x + d[S],
              w = x - d[b];
            x = Vr(C, x, w);
          }
          const v = f.fn({ ...t, [g]: h, [p]: x });
          return {
            ...v,
            data: { x: v.x - n, y: v.y - r, enabled: { [g]: i, [p]: a } },
          };
        },
      }
    );
  },
  ju = function (e) {
    return (
      e === void 0 && (e = {}),
      {
        options: e,
        fn(t) {
          const { x: n, y: r, placement: s, rects: o, middlewareData: i } = t,
            { offset: a = 0, mainAxis: f = !0, crossAxis: u = !0 } = Ot(e, t),
            l = { x: n, y: r },
            d = lt(s),
            p = ls(d);
          let g = l[p],
            h = l[d];
          const x = Ot(a, t),
            v =
              typeof x == "number"
                ? { mainAxis: x, crossAxis: 0 }
                : { mainAxis: 0, crossAxis: 0, ...x };
          if (f) {
            const C = p === "y" ? "height" : "width",
              w = o.reference[p] - o.floating[C] + v.mainAxis,
              R = o.reference[p] + o.reference[C] - v.mainAxis;
            g < w ? (g = w) : g > R && (g = R);
          }
          if (u) {
            var S, b;
            const C = p === "y" ? "width" : "height",
              w = Mi.has(tt(s)),
              R =
                o.reference[d] -
                o.floating[C] +
                ((w && ((S = i.offset) == null ? void 0 : S[d])) || 0) +
                (w ? 0 : v.crossAxis),
              E =
                o.reference[d] +
                o.reference[C] +
                (w ? 0 : ((b = i.offset) == null ? void 0 : b[d]) || 0) -
                (w ? v.crossAxis : 0);
            h < R ? (h = R) : h > E && (h = E);
          }
          return { [p]: g, [d]: h };
        },
      }
    );
  },
  Iu = function (e) {
    return (
      e === void 0 && (e = {}),
      {
        name: "size",
        options: e,
        async fn(t) {
          var n, r;
          const { placement: s, rects: o, platform: i, elements: a } = t,
            { apply: f = () => {}, ...u } = Ot(e, t),
            l = await i.detectOverflow(t, u),
            d = tt(s),
            p = _t(s),
            g = lt(s) === "y",
            { width: h, height: x } = o.floating;
          let v, S;
          d === "top" || d === "bottom"
            ? ((v = d),
              (S =
                p ===
                ((await (i.isRTL == null ? void 0 : i.isRTL(a.floating)))
                  ? "start"
                  : "end")
                  ? "left"
                  : "right"))
            : ((S = d), (v = p === "end" ? "top" : "bottom"));
          const b = x - l.top - l.bottom,
            C = h - l.left - l.right,
            w = sn(x - l[v], b),
            R = sn(h - l[S], C),
            E = !t.middlewareData.shift;
          let T = w,
            O = R;
          if (
            ((n = t.middlewareData.shift) != null && n.enabled.x && (O = C),
            (r = t.middlewareData.shift) != null && r.enabled.y && (T = b),
            E && !p)
          ) {
            const j = ot(l.left, 0),
              $ = ot(l.right, 0),
              P = ot(l.top, 0),
              I = ot(l.bottom, 0);
            g
              ? (O = h - 2 * (j !== 0 || $ !== 0 ? j + $ : ot(l.left, l.right)))
              : (T =
                  x - 2 * (P !== 0 || I !== 0 ? P + I : ot(l.top, l.bottom)));
          }
          await f({ ...t, availableWidth: O, availableHeight: T });
          const A = await i.getDimensions(a.floating);
          return h !== A.width || x !== A.height
            ? { reset: { rects: !0 } }
            : {};
        },
      }
    );
  };
function Di(e) {
  const t = nt(e);
  let n = parseFloat(t.width) || 0,
    r = parseFloat(t.height) || 0;
  const s = Le(e),
    o = s ? e.offsetWidth : n,
    i = s ? e.offsetHeight : r,
    a = Wn(n) !== o || Wn(r) !== i;
  return (a && ((n = o), (r = i)), { width: n, height: r, $: a });
}
function xs(e) {
  return he(e) ? e : e.contextElement;
}
function nn(e) {
  const t = xs(e);
  if (!Le(t)) return St(1);
  const n = t.getBoundingClientRect(),
    { width: r, height: s, $: o } = Di(t);
  let i = (o ? Wn(n.width) : n.width) / r,
    a = (o ? Wn(n.height) : n.height) / s;
  return (
    (!i || !Number.isFinite(i)) && (i = 1),
    (!a || !Number.isFinite(a)) && (a = 1),
    { x: i, y: a }
  );
}
const Nu = St(0);
function Li(e) {
  const t = Ge(e);
  return !tr() || !t.visualViewport
    ? Nu
    : { x: t.visualViewport.offsetLeft, y: t.visualViewport.offsetTop };
}
function Pu(e, t, n) {
  return (t === void 0 && (t = !1), !n || (t && n !== Ge(e)) ? !1 : t);
}
function Xt(e, t, n, r) {
  (t === void 0 && (t = !1), n === void 0 && (n = !1));
  const s = e.getBoundingClientRect(),
    o = xs(e);
  let i = St(1);
  t && (r ? he(r) && (i = nn(r)) : (i = nn(e)));
  const a = Pu(o, n, r) ? Li(o) : St(0);
  let f = (s.left + a.x) / i.x,
    u = (s.top + a.y) / i.y,
    l = s.width / i.x,
    d = s.height / i.y;
  if (o) {
    const p = Ge(o),
      g = r && he(r) ? Ge(r) : r;
    let h = p,
      x = Wr(h);
    for (; x && r && g !== h; ) {
      const v = nn(x),
        S = x.getBoundingClientRect(),
        b = nt(x),
        C = S.left + (x.clientLeft + parseFloat(b.paddingLeft)) * v.x,
        w = S.top + (x.clientTop + parseFloat(b.paddingTop)) * v.y;
      ((f *= v.x),
        (u *= v.y),
        (l *= v.x),
        (d *= v.y),
        (f += C),
        (u += w),
        (h = Ge(x)),
        (x = Wr(h)));
    }
  }
  return Vn({ width: l, height: d, x: f, y: u });
}
function or(e, t) {
  const n = nr(e).scrollLeft;
  return t ? t.left + n : Xt(wt(e)).left + n;
}
function Fi(e, t) {
  const n = e.getBoundingClientRect(),
    r = n.left + t.scrollLeft - or(e, n),
    s = n.top + t.scrollTop;
  return { x: r, y: s };
}
function Bu(e) {
  let { elements: t, rect: n, offsetParent: r, strategy: s } = e;
  const o = s === "fixed",
    i = wt(r),
    a = t ? er(t.floating) : !1;
  if (r === i || (a && o)) return n;
  let f = { scrollLeft: 0, scrollTop: 0 },
    u = St(1);
  const l = St(0),
    d = Le(r);
  if ((d || (!d && !o)) && ((ze(r) !== "body" || Ht(i)) && (f = nr(r)), d)) {
    const g = Xt(r);
    ((u = nn(r)), (l.x = g.x + r.clientLeft), (l.y = g.y + r.clientTop));
  }
  const p = i && !d && !o ? Fi(i, f) : St(0);
  return {
    width: n.width * u.x,
    height: n.height * u.y,
    x: n.x * u.x - f.scrollLeft * u.x + l.x + p.x,
    y: n.y * u.y - f.scrollTop * u.y + l.y + p.y,
  };
}
function Mu(e) {
  return Array.from(e.getClientRects());
}
function Du(e) {
  const t = wt(e),
    n = nr(e),
    r = e.ownerDocument.body,
    s = ot(t.scrollWidth, t.clientWidth, r.scrollWidth, r.clientWidth),
    o = ot(t.scrollHeight, t.clientHeight, r.scrollHeight, r.clientHeight);
  let i = -n.scrollLeft + or(e);
  const a = -n.scrollTop;
  return (
    nt(r).direction === "rtl" && (i += ot(t.clientWidth, r.clientWidth) - s),
    { width: s, height: o, x: i, y: a }
  );
}
const ao = 25;
function Lu(e, t) {
  const n = Ge(e),
    r = wt(e),
    s = n.visualViewport;
  let o = r.clientWidth,
    i = r.clientHeight,
    a = 0,
    f = 0;
  if (s) {
    ((o = s.width), (i = s.height));
    const l = tr();
    (!l || (l && t === "fixed")) && ((a = s.offsetLeft), (f = s.offsetTop));
  }
  const u = or(r);
  if (u <= 0) {
    const l = r.ownerDocument,
      d = l.body,
      p = getComputedStyle(d),
      g =
        (l.compatMode === "CSS1Compat" &&
          parseFloat(p.marginLeft) + parseFloat(p.marginRight)) ||
        0,
      h = Math.abs(r.clientWidth - d.clientWidth - g);
    h <= ao && (o -= h);
  } else u <= ao && (o += u);
  return { width: o, height: i, x: a, y: f };
}
function Fu(e, t) {
  const n = Xt(e, !0, t === "fixed"),
    r = n.top + e.clientTop,
    s = n.left + e.clientLeft,
    o = Le(e) ? nn(e) : St(1),
    i = e.clientWidth * o.x,
    a = e.clientHeight * o.y,
    f = s * o.x,
    u = r * o.y;
  return { width: i, height: a, x: f, y: u };
}
function lo(e, t, n) {
  let r;
  if (t === "viewport") r = Lu(e, n);
  else if (t === "document") r = Du(wt(e));
  else if (he(t)) r = Fu(t, n);
  else {
    const s = Li(e);
    r = { x: t.x - s.x, y: t.y - s.y, width: t.width, height: t.height };
  }
  return Vn(r);
}
function Hi(e, t) {
  const n = At(e);
  return n === t || !he(n) || kt(n)
    ? !1
    : nt(n).position === "fixed" || Hi(n, t);
}
function Hu(e, t) {
  const n = t.get(e);
  if (n) return n;
  let r = gn(e, [], !1).filter((a) => he(a) && ze(a) !== "body"),
    s = null;
  const o = nt(e).position === "fixed";
  let i = o ? At(e) : e;
  for (; he(i) && !kt(i); ) {
    const a = nt(i),
      f = rs(i);
    (!f && a.position === "fixed" && (s = null),
      (
        o
          ? !f && !s
          : (!f &&
              a.position === "static" &&
              !!s &&
              (s.position === "absolute" || s.position === "fixed")) ||
            (Ht(i) && !f && Hi(e, i))
      )
        ? (r = r.filter((l) => l !== i))
        : (s = a),
      (i = At(i)));
  }
  return (t.set(e, r), r);
}
function _u(e) {
  let { element: t, boundary: n, rootBoundary: r, strategy: s } = e;
  const i = [
      ...(n === "clippingAncestors"
        ? er(t)
          ? []
          : Hu(t, this._c)
        : [].concat(n)),
      r,
    ],
    a = lo(t, i[0], s);
  let f = a.top,
    u = a.right,
    l = a.bottom,
    d = a.left;
  for (let p = 1; p < i.length; p++) {
    const g = lo(t, i[p], s);
    ((f = ot(g.top, f)),
      (u = sn(g.right, u)),
      (l = sn(g.bottom, l)),
      (d = ot(g.left, d)));
  }
  return { width: u - d, height: l - f, x: d, y: f };
}
function $u(e) {
  const { width: t, height: n } = Di(e);
  return { width: t, height: n };
}
function Gu(e, t, n) {
  const r = Le(t),
    s = wt(t),
    o = n === "fixed",
    i = Xt(e, !0, o, t);
  let a = { scrollLeft: 0, scrollTop: 0 };
  const f = St(0);
  function u() {
    f.x = or(s);
  }
  if (r || (!r && !o))
    if (((ze(t) !== "body" || Ht(s)) && (a = nr(t)), r)) {
      const g = Xt(t, !0, o, t);
      ((f.x = g.x + t.clientLeft), (f.y = g.y + t.clientTop));
    } else s && u();
  o && !r && s && u();
  const l = s && !r && !o ? Fi(s, a) : St(0),
    d = i.left + a.scrollLeft - f.x - l.x,
    p = i.top + a.scrollTop - f.y - l.y;
  return { x: d, y: p, width: i.width, height: i.height };
}
function Nr(e) {
  return nt(e).position === "static";
}
function co(e, t) {
  if (!Le(e) || nt(e).position === "fixed") return null;
  if (t) return t(e);
  let n = e.offsetParent;
  return (wt(e) === n && (n = n.ownerDocument.body), n);
}
function _i(e, t) {
  const n = Ge(e);
  if (er(e)) return n;
  if (!Le(e)) {
    let s = At(e);
    for (; s && !kt(s); ) {
      if (he(s) && !Nr(s)) return s;
      s = At(s);
    }
    return n;
  }
  let r = co(e, t);
  for (; r && rc(r) && Nr(r); ) r = co(r, t);
  return r && kt(r) && Nr(r) && !rs(r) ? n : r || ic(e) || n;
}
const Uu = async function (e) {
  const t = this.getOffsetParent || _i,
    n = this.getDimensions,
    r = await n(e.floating);
  return {
    reference: Gu(e.reference, await t(e.floating), e.strategy),
    floating: { x: 0, y: 0, width: r.width, height: r.height },
  };
};
function Wu(e) {
  return nt(e).direction === "rtl";
}
const Ku = {
  convertOffsetParentRelativeRectToViewportRelativeRect: Bu,
  getDocumentElement: wt,
  getClippingRect: _u,
  getOffsetParent: _i,
  getElementRects: Uu,
  getClientRects: Mu,
  getDimensions: $u,
  getScale: nn,
  isElement: he,
  isRTL: Wu,
};
function $i(e, t) {
  return (
    e.x === t.x && e.y === t.y && e.width === t.width && e.height === t.height
  );
}
function Vu(e, t) {
  let n = null,
    r;
  const s = wt(e);
  function o() {
    var a;
    (clearTimeout(r), (a = n) == null || a.disconnect(), (n = null));
  }
  function i(a, f) {
    (a === void 0 && (a = !1), f === void 0 && (f = 1), o());
    const u = e.getBoundingClientRect(),
      { left: l, top: d, width: p, height: g } = u;
    if ((a || t(), !p || !g)) return;
    const h = jn(d),
      x = jn(s.clientWidth - (l + p)),
      v = jn(s.clientHeight - (d + g)),
      S = jn(l),
      C = {
        rootMargin: -h + "px " + -x + "px " + -v + "px " + -S + "px",
        threshold: ot(0, sn(1, f)) || 1,
      };
    let w = !0;
    function R(E) {
      const T = E[0].intersectionRatio;
      if (T !== f) {
        if (!w) return i();
        T
          ? i(!1, T)
          : (r = setTimeout(() => {
              i(!1, 1e-7);
            }, 1e3));
      }
      (T === 1 && !$i(u, e.getBoundingClientRect()) && i(), (w = !1));
    }
    try {
      n = new IntersectionObserver(R, { ...C, root: s.ownerDocument });
    } catch {
      n = new IntersectionObserver(R, C);
    }
    n.observe(e);
  }
  return (i(!0), o);
}
function uo(e, t, n, r) {
  r === void 0 && (r = {});
  const {
      ancestorScroll: s = !0,
      ancestorResize: o = !0,
      elementResize: i = typeof ResizeObserver == "function",
      layoutShift: a = typeof IntersectionObserver == "function",
      animationFrame: f = !1,
    } = r,
    u = xs(e),
    l = s || o ? [...(u ? gn(u) : []), ...(t ? gn(t) : [])] : [];
  l.forEach((S) => {
    (s && S.addEventListener("scroll", n, { passive: !0 }),
      o && S.addEventListener("resize", n));
  });
  const d = u && a ? Vu(u, n) : null;
  let p = -1,
    g = null;
  i &&
    ((g = new ResizeObserver((S) => {
      let [b] = S;
      (b &&
        b.target === u &&
        g &&
        t &&
        (g.unobserve(t),
        cancelAnimationFrame(p),
        (p = requestAnimationFrame(() => {
          var C;
          (C = g) == null || C.observe(t);
        }))),
        n());
    })),
    u && !f && g.observe(u),
    t && g.observe(t));
  let h,
    x = f ? Xt(e) : null;
  f && v();
  function v() {
    const S = Xt(e);
    (x && !$i(x, S) && n(), (x = S), (h = requestAnimationFrame(v)));
  }
  return (
    n(),
    () => {
      var S;
      (l.forEach((b) => {
        (s && b.removeEventListener("scroll", n),
          o && b.removeEventListener("resize", n));
      }),
        d?.(),
        (S = g) == null || S.disconnect(),
        (g = null),
        f && cancelAnimationFrame(h));
    }
  );
}
const Yu = Au,
  Xu = Ou,
  zu = Eu,
  qu = Iu,
  Zu = Ru,
  Qu = ju,
  Ju = (e, t, n) => {
    const r = new Map(),
      s = { platform: Ku, ...n },
      o = { ...s.platform, _c: r };
    return Tu(e, t, { ...s, platform: o });
  };
var ed = typeof document < "u",
  td = function () {},
  Ln = ed ? m.useLayoutEffect : td;
function zn(e, t) {
  if (e === t) return !0;
  if (typeof e != typeof t) return !1;
  if (typeof e == "function" && e.toString() === t.toString()) return !0;
  let n, r, s;
  if (e && t && typeof e == "object") {
    if (Array.isArray(e)) {
      if (((n = e.length), n !== t.length)) return !1;
      for (r = n; r-- !== 0; ) if (!zn(e[r], t[r])) return !1;
      return !0;
    }
    if (((s = Object.keys(e)), (n = s.length), n !== Object.keys(t).length))
      return !1;
    for (r = n; r-- !== 0; ) if (!{}.hasOwnProperty.call(t, s[r])) return !1;
    for (r = n; r-- !== 0; ) {
      const o = s[r];
      if (!(o === "_owner" && e.$$typeof) && !zn(e[o], t[o])) return !1;
    }
    return !0;
  }
  return e !== e && t !== t;
}
function Gi(e) {
  return typeof window > "u"
    ? 1
    : (e.ownerDocument.defaultView || window).devicePixelRatio || 1;
}
function fo(e, t) {
  const n = Gi(e);
  return Math.round(t * n) / n;
}
function Pr(e) {
  const t = m.useRef(e);
  return (
    Ln(() => {
      t.current = e;
    }),
    t
  );
}
function nd(e) {
  e === void 0 && (e = {});
  const {
      placement: t = "bottom",
      strategy: n = "absolute",
      middleware: r = [],
      platform: s,
      elements: { reference: o, floating: i } = {},
      transform: a = !0,
      whileElementsMounted: f,
      open: u,
    } = e,
    [l, d] = m.useState({
      x: 0,
      y: 0,
      strategy: n,
      placement: t,
      middlewareData: {},
      isPositioned: !1,
    }),
    [p, g] = m.useState(r);
  zn(p, r) || g(r);
  const [h, x] = m.useState(null),
    [v, S] = m.useState(null),
    b = m.useCallback((N) => {
      N !== E.current && ((E.current = N), x(N));
    }, []),
    C = m.useCallback((N) => {
      N !== T.current && ((T.current = N), S(N));
    }, []),
    w = o || h,
    R = i || v,
    E = m.useRef(null),
    T = m.useRef(null),
    O = m.useRef(l),
    A = f != null,
    j = Pr(f),
    $ = Pr(s),
    P = Pr(u),
    I = m.useCallback(() => {
      if (!E.current || !T.current) return;
      const N = { placement: t, strategy: n, middleware: p };
      ($.current && (N.platform = $.current),
        Ju(E.current, T.current, N).then((D) => {
          const U = { ...D, isPositioned: P.current !== !1 };
          L.current &&
            !zn(O.current, U) &&
            ((O.current = U),
            zt.flushSync(() => {
              d(U);
            }));
        }));
    }, [p, t, n, $, P]);
  Ln(() => {
    u === !1 &&
      O.current.isPositioned &&
      ((O.current.isPositioned = !1), d((N) => ({ ...N, isPositioned: !1 })));
  }, [u]);
  const L = m.useRef(!1);
  (Ln(
    () => (
      (L.current = !0),
      () => {
        L.current = !1;
      }
    ),
    [],
  ),
    Ln(() => {
      if ((w && (E.current = w), R && (T.current = R), w && R)) {
        if (j.current) return j.current(w, R, I);
        I();
      }
    }, [w, R, I, j, A]));
  const k = m.useMemo(
      () => ({ reference: E, floating: T, setReference: b, setFloating: C }),
      [b, C],
    ),
    M = m.useMemo(() => ({ reference: w, floating: R }), [w, R]),
    H = m.useMemo(() => {
      const N = { position: n, left: 0, top: 0 };
      if (!M.floating) return N;
      const D = fo(M.floating, l.x),
        U = fo(M.floating, l.y);
      return a
        ? {
            ...N,
            transform: "translate(" + D + "px, " + U + "px)",
            ...(Gi(M.floating) >= 1.5 && { willChange: "transform" }),
          }
        : { position: n, left: D, top: U };
    }, [n, a, M.floating, l.x, l.y]);
  return m.useMemo(
    () => ({ ...l, update: I, refs: k, elements: M, floatingStyles: H }),
    [l, I, k, M, H],
  );
}
const rd = (e, t) => {
    const n = Yu(e);
    return { name: n.name, fn: n.fn, options: [e, t] };
  },
  sd = (e, t) => {
    const n = Xu(e);
    return { name: n.name, fn: n.fn, options: [e, t] };
  },
  od = (e, t) => ({ fn: Qu(e).fn, options: [e, t] }),
  id = (e, t) => {
    const n = zu(e);
    return { name: n.name, fn: n.fn, options: [e, t] };
  },
  ad = (e, t) => {
    const n = qu(e);
    return { name: n.name, fn: n.fn, options: [e, t] };
  },
  ld = (e, t) => {
    const n = Zu(e);
    return { name: n.name, fn: n.fn, options: [e, t] };
  },
  ae = (e, t, n, r, s, o, ...i) => {
    if (i.length > 0) throw new Error(It(1));
    let a;
    if (e) a = e;
    else throw new Error("Missing arguments");
    return a;
  };
var Br = { exports: {} },
  Mr = {};
var po;
function cd() {
  if (po) return Mr;
  po = 1;
  var e = Do();
  function t(d, p) {
    return (d === p && (d !== 0 || 1 / d === 1 / p)) || (d !== d && p !== p);
  }
  var n = typeof Object.is == "function" ? Object.is : t,
    r = e.useState,
    s = e.useEffect,
    o = e.useLayoutEffect,
    i = e.useDebugValue;
  function a(d, p) {
    var g = p(),
      h = r({ inst: { value: g, getSnapshot: p } }),
      x = h[0].inst,
      v = h[1];
    return (
      o(
        function () {
          ((x.value = g), (x.getSnapshot = p), f(x) && v({ inst: x }));
        },
        [d, g, p],
      ),
      s(
        function () {
          return (
            f(x) && v({ inst: x }),
            d(function () {
              f(x) && v({ inst: x });
            })
          );
        },
        [d],
      ),
      i(g),
      g
    );
  }
  function f(d) {
    var p = d.getSnapshot;
    d = d.value;
    try {
      var g = p();
      return !n(d, g);
    } catch {
      return !0;
    }
  }
  function u(d, p) {
    return p();
  }
  var l =
    typeof window > "u" ||
    typeof window.document > "u" ||
    typeof window.document.createElement > "u"
      ? u
      : a;
  return (
    (Mr.useSyncExternalStore =
      e.useSyncExternalStore !== void 0 ? e.useSyncExternalStore : l),
    Mr
  );
}
var ho;
function Ui() {
  return (ho || ((ho = 1), (Br.exports = cd())), Br.exports);
}
var Wi = Ui(),
  Dr = { exports: {} },
  Lr = {};
var mo;
function ud() {
  if (mo) return Lr;
  mo = 1;
  var e = Do(),
    t = Ui();
  function n(u, l) {
    return (u === l && (u !== 0 || 1 / u === 1 / l)) || (u !== u && l !== l);
  }
  var r = typeof Object.is == "function" ? Object.is : n,
    s = t.useSyncExternalStore,
    o = e.useRef,
    i = e.useEffect,
    a = e.useMemo,
    f = e.useDebugValue;
  return (
    (Lr.useSyncExternalStoreWithSelector = function (u, l, d, p, g) {
      var h = o(null);
      if (h.current === null) {
        var x = { hasValue: !1, value: null };
        h.current = x;
      } else x = h.current;
      h = a(
        function () {
          function S(E) {
            if (!b) {
              if (((b = !0), (C = E), (E = p(E)), g !== void 0 && x.hasValue)) {
                var T = x.value;
                if (g(T, E)) return (w = T);
              }
              return (w = E);
            }
            if (((T = w), r(C, E))) return T;
            var O = p(E);
            return g !== void 0 && g(T, O) ? ((C = E), T) : ((C = E), (w = O));
          }
          var b = !1,
            C,
            w,
            R = d === void 0 ? null : d;
          return [
            function () {
              return S(l());
            },
            R === null
              ? void 0
              : function () {
                  return S(R());
                },
          ];
        },
        [l, d, p, g],
      );
      var v = s(u, h[0], h[1]);
      return (
        i(
          function () {
            ((x.hasValue = !0), (x.value = v));
          },
          [v],
        ),
        f(v),
        v
      );
    }),
    Lr
  );
}
var go;
function dd() {
  return (go || ((go = 1), (Dr.exports = ud())), Dr.exports);
}
var fd = dd();
const pd = fs(19),
  hd = pd ? gd : xd;
function Ki(e, t, n, r, s) {
  return hd(e, t, n, r, s);
}
function md(e, t, n, r, s) {
  const o = m.useCallback(() => t(e.getSnapshot(), n, r, s), [e, t, n, r, s]);
  return Wi.useSyncExternalStore(e.subscribe, o, o);
}
$l({
  before(e) {
    ((e.syncIndex = 0),
      e.didInitialize ||
        ((e.syncTick = 1),
        (e.syncHooks = []),
        (e.didChangeStore = !0),
        (e.getSnapshot = () => {
          let t = !1;
          for (let n = 0; n < e.syncHooks.length; n += 1) {
            const r = e.syncHooks[n],
              s = r.selector(r.store.state, r.a1, r.a2, r.a3);
            (r.didChange || !Object.is(r.value, s)) &&
              ((t = !0), (r.value = s), (r.didChange = !1));
          }
          return (t && (e.syncTick += 1), e.syncTick);
        })));
  },
  after(e) {
    e.syncHooks.length > 0 &&
      (e.didChangeStore &&
        ((e.didChangeStore = !1),
        (e.subscribe = (t) => {
          const n = new Set();
          for (const s of e.syncHooks) n.add(s.store);
          const r = [];
          for (const s of n) r.push(s.subscribe(t));
          return () => {
            for (const s of r) s();
          };
        })),
      Wi.useSyncExternalStore(e.subscribe, e.getSnapshot, e.getSnapshot));
  },
});
function gd(e, t, n, r, s) {
  const o = _l();
  if (!o) return md(e, t, n, r, s);
  const i = o.syncIndex;
  o.syncIndex += 1;
  let a;
  return (
    o.didInitialize
      ? ((a = o.syncHooks[i]),
        (a.store !== e ||
          a.selector !== t ||
          !Object.is(a.a1, n) ||
          !Object.is(a.a2, r) ||
          !Object.is(a.a3, s)) &&
          (a.store !== e && (o.didChangeStore = !0),
          (a.store = e),
          (a.selector = t),
          (a.a1 = n),
          (a.a2 = r),
          (a.a3 = s),
          (a.didChange = !0)))
      : ((a = {
          store: e,
          selector: t,
          a1: n,
          a2: r,
          a3: s,
          value: t(e.getSnapshot(), n, r, s),
          didChange: !1,
        }),
        o.syncHooks.push(a)),
    a.value
  );
}
function xd(e, t, n, r, s) {
  return fd.useSyncExternalStoreWithSelector(
    e.subscribe,
    e.getSnapshot,
    e.getSnapshot,
    (o) => t(o, n, r, s),
  );
}
class bd {
  constructor(t) {
    ((this.state = t), (this.listeners = new Set()), (this.updateTick = 0));
  }
  subscribe = (t) => (
    this.listeners.add(t),
    () => {
      this.listeners.delete(t);
    }
  );
  getSnapshot = () => this.state;
  setState(t) {
    if (this.state === t) return;
    ((this.state = t), (this.updateTick += 1));
    const n = this.updateTick;
    for (const r of this.listeners) {
      if (n !== this.updateTick) return;
      r(t);
    }
  }
  update(t) {
    for (const n in t)
      if (!Object.is(this.state[n], t[n])) {
        this.setState({ ...this.state, ...t });
        return;
      }
  }
  set(t, n) {
    Object.is(this.state[t], n) || this.setState({ ...this.state, [t]: n });
  }
  notifyAll() {
    const t = { ...this.state };
    this.setState(t);
  }
  use(t, n, r, s) {
    return Ki(this, t, n, r, s);
  }
}
class bs extends bd {
  constructor(t, n = {}, r) {
    (super(t), (this.context = n), (this.selectors = r));
  }
  useSyncedValue(t, n) {
    m.useDebugValue(t);
    const r = this;
    xe(() => {
      r.state[t] !== n && r.set(t, n);
    }, [r, t, n]);
  }
  useSyncedValueWithCleanup(t, n) {
    const r = this;
    xe(
      () => (
        r.state[t] !== n && r.set(t, n),
        () => {
          r.set(t, void 0);
        }
      ),
      [r, t, n],
    );
  }
  useSyncedValues(t) {
    const n = this,
      r = Object.values(t);
    xe(() => {
      n.update(t);
    }, [n, ...r]);
  }
  useControlledProp(t, n) {
    m.useDebugValue(t);
    const r = this,
      s = n !== void 0;
    xe(() => {
      s && !Object.is(r.state[t], n) && r.setState({ ...r.state, [t]: n });
    }, [r, t, n, s]);
  }
  select(t, n, r, s) {
    const o = this.selectors[t];
    return o(this.state, n, r, s);
  }
  useState(t, n, r, s) {
    return (m.useDebugValue(t), Ki(this, this.selectors[t], n, r, s));
  }
  useContextCallback(t, n) {
    m.useDebugValue(t);
    const r = Te(n ?? os);
    this.context[t] = r;
  }
  useStateSetter(t) {
    const n = m.useRef(void 0);
    return (
      n.current === void 0 &&
        (n.current = (r) => {
          this.set(t, r);
        }),
      n.current
    );
  }
  observe(t, n) {
    let r;
    typeof t == "function" ? (r = t) : (r = this.selectors[t]);
    let s = r(this.state);
    return (
      n(s, s, this),
      this.subscribe((o) => {
        const i = r(o);
        if (!Object.is(s, i)) {
          const a = s;
          ((s = i), n(i, a, this));
        }
      })
    );
  }
}
const vd = {
  open: ae((e) => e.open),
  transitionStatus: ae((e) => e.transitionStatus),
  domReferenceElement: ae((e) => e.domReferenceElement),
  referenceElement: ae((e) => e.positionReference ?? e.referenceElement),
  floatingElement: ae((e) => e.floatingElement),
  floatingId: ae((e) => e.floatingId),
};
class ir extends bs {
  constructor(t) {
    const {
      syncOnly: n,
      nested: r,
      onOpenChange: s,
      triggerElements: o,
      ...i
    } = t;
    (super(
      {
        ...i,
        positionReference: i.referenceElement,
        domReferenceElement: i.referenceElement,
      },
      {
        onOpenChange: s,
        dataRef: { current: {} },
        events: uu(),
        nested: r,
        triggerElements: o,
      },
      vd,
    ),
      (this.syncOnly = n));
  }
  syncOpenEvent = (t, n) => {
    (!t || !this.state.open || (n != null && nc(n))) &&
      (this.context.dataRef.current.openEvent = t ? n : void 0);
  };
  dispatchOpenChange = (t, n) => {
    this.syncOpenEvent(t, n.event);
    const r = {
      open: t,
      reason: n.reason,
      nativeEvent: n.event,
      nested: this.context.nested,
      triggerElement: n.trigger,
    };
    this.context.events.emit("openchange", r);
  };
  setOpen = (t, n) => {
    if (this.syncOnly) {
      this.context.onOpenChange?.(t, n);
      return;
    }
    (this.dispatchOpenChange(t, n), this.context.onOpenChange?.(t, n));
  };
}
function yd(e) {
  const {
      popupStore: t,
      treatPopupAsFloatingElement: n = !1,
      floatingRootContext: r,
      floatingId: s,
      nested: o,
      onOpenChange: i,
    } = e,
    a = t.useState("open"),
    f = t.useState("activeTriggerElement"),
    u = t.useState(n ? "popupElement" : "positionerElement"),
    l = t.context.triggerElements,
    d = i,
    p = m.useRef(null);
  r === void 0 &&
    p.current === null &&
    (p.current = new ir({
      open: a,
      transitionStatus: void 0,
      referenceElement: f,
      floatingElement: u,
      triggerElements: l,
      onOpenChange: d,
      floatingId: s,
      syncOnly: !0,
      nested: o,
    }));
  const g = r ?? p.current;
  return (
    t.useSyncedValue("floatingId", s),
    xe(() => {
      const h = {
        open: a,
        floatingId: s,
        referenceElement: f,
        floatingElement: u,
      };
      (he(f) && (h.domReferenceElement = f),
        g.state.positionReference === g.state.referenceElement &&
          (h.positionReference = f),
        g.update(h));
    }, [a, s, f, u, g]),
    (g.context.onOpenChange = d),
    (g.context.nested = o),
    g
  );
}
function Sd(e, t = !1, n = !1) {
  const [r, s] = m.useState(e && t ? "idle" : void 0),
    [o, i] = m.useState(e);
  return (
    e && !o && (i(!0), s("starting")),
    !e && o && r !== "ending" && !n && s("ending"),
    !e && !o && r === "ending" && s(void 0),
    xe(() => {
      if (!e && o && r !== "ending" && n) {
        const a = vt.request(() => {
          s("ending");
        });
        return () => {
          vt.cancel(a);
        };
      }
    }, [e, o, r, n]),
    xe(() => {
      if (!e || t) return;
      const a = vt.request(() => {
        s(void 0);
      });
      return () => {
        vt.cancel(a);
      };
    }, [t, e]),
    xe(() => {
      if (!e || !t) return;
      e && o && r !== "idle" && s("starting");
      const a = vt.request(() => {
        s("idle");
      });
      return () => {
        vt.cancel(a);
      };
    }, [t, e, o, r]),
    { mounted: o, setMounted: i, transitionStatus: r }
  );
}
let bn = (function (e) {
  return (
    (e.startingStyle = "data-starting-style"),
    (e.endingStyle = "data-ending-style"),
    e
  );
})({});
const wd = { [bn.startingStyle]: "" },
  Cd = { [bn.endingStyle]: "" },
  vs = {
    transitionStatus(e) {
      return e === "starting" ? wd : e === "ending" ? Cd : null;
    },
  };
function Td(e, t = !1, n = !0) {
  const r = fi();
  return Te((s, o = null) => {
    r.cancel();
    const i = Et(e);
    if (i == null) return;
    const a = i,
      f = () => {
        zt.flushSync(s);
      };
    if (
      typeof a.getAnimations != "function" ||
      globalThis.BASE_UI_ANIMATIONS_DISABLED
    ) {
      s();
      return;
    }
    function u() {
      Promise.all(a.getAnimations().map((l) => l.finished))
        .then(() => {
          o?.aborted || f();
        })
        .catch(() => {
          if (n) {
            o?.aborted || f();
            return;
          }
          const l = a.getAnimations();
          !o?.aborted &&
            l.length > 0 &&
            l.some((d) => d.pending || d.playState !== "finished") &&
            u();
        });
    }
    if (t) {
      const l = bn.startingStyle;
      if (!a.hasAttribute(l)) {
        r.request(u);
        return;
      }
      const d = new MutationObserver(() => {
        a.hasAttribute(l) || (d.disconnect(), u());
      });
      (d.observe(a, { attributes: !0, attributeFilter: [l] }),
        o?.addEventListener("abort", () => d.disconnect(), { once: !0 }));
      return;
    }
    r.request(u);
  });
}
function ys(e) {
  const { enabled: t = !0, open: n, ref: r, onComplete: s } = e,
    o = Te(s),
    i = Td(r, n, !1);
  m.useEffect(() => {
    if (!t) return;
    const a = new AbortController();
    return (
      i(o, a.signal),
      () => {
        a.abort();
      }
    );
  }, [t, n, o, i]);
}
const Ss = { tabIndex: -1, [Kr]: "" };
function Vi(e, t, n = !1) {
  const r = sr(),
    s = ms() != null,
    o = m.useRef(null);
  e === void 0 && o.current === null && (o.current = t(r, s));
  const i = e ?? o.current;
  return (
    yd({
      popupStore: i,
      treatPopupAsFloatingElement: n,
      floatingRootContext: i.state.floatingRootContext,
      floatingId: r,
      nested: s,
      onOpenChange: i.setOpen,
    }),
    { store: i, internalStore: o.current }
  );
}
function Ed(e, t) {
  const n = m.useRef(null),
    r = m.useRef(null);
  return m.useCallback(
    (s) => {
      if (e === void 0) return;
      let o = !1;
      if (n.current !== null) {
        const i = n.current,
          a = r.current,
          f = t.context.triggerElements.getById(i);
        (a && f === a && (t.context.triggerElements.delete(i), (o = !0)),
          (n.current = null),
          (r.current = null));
      }
      if (
        (s !== null &&
          ((n.current = e),
          (r.current = s),
          t.context.triggerElements.add(e, s),
          (o = !0)),
        o)
      ) {
        const i = t.context.triggerElements.size;
        t.select("open") &&
          t.state.triggerCount !== i &&
          t.set("triggerCount", i);
      }
    },
    [t, e],
  );
}
function Yi(e, t, n) {
  const r = n?.id ?? null;
  (r || t) && ((e.activeTriggerId = r), (e.activeTriggerElement = n ?? null));
}
function Rd(e, t, n, r) {
  const s = n.useState("isMountedByTrigger", e),
    o = Ed(e, n),
    i = Te((a) => {
      if ((o(a), !a)) return;
      const f = n.select("open"),
        u = n.select("activeTriggerId");
      if (u === e) {
        n.update({ activeTriggerElement: a, ...(f ? r : null) });
        return;
      }
      u == null &&
        f &&
        n.update({ activeTriggerId: e, activeTriggerElement: a, ...r });
    });
  return (
    xe(() => {
      s && n.update({ activeTriggerElement: t.current, ...r });
    }, [s, n, t, ...Object.values(r)]),
    { registerTrigger: i, isMountedByThisTrigger: s }
  );
}
function Xi(e) {
  const t = e.useState("open"),
    n = e.useState("triggerCount");
  xe(() => {
    if (!t) {
      e.state.triggerCount !== 0 && e.set("triggerCount", 0);
      return;
    }
    const r = e.context.triggerElements.size,
      s = {};
    if (
      (e.state.triggerCount !== r && (s.triggerCount = r),
      !e.select("activeTriggerId") && r === 1)
    ) {
      const o = e.context.triggerElements.entries().next();
      if (!o.done) {
        const [i, a] = o.value;
        ((s.activeTriggerId = i), (s.activeTriggerElement = a));
      }
    }
    (s.triggerCount !== void 0 || s.activeTriggerId !== void 0) && e.update(s);
  }, [t, e, n]);
}
function zi(e, t, n) {
  const { mounted: r, setMounted: s, transitionStatus: o } = Sd(e);
  t.useSyncedValues({ mounted: r, transitionStatus: o });
  const i = Te(() => {
      (s(!1),
        t.update({
          activeTriggerId: null,
          activeTriggerElement: null,
          mounted: !1,
          preventUnmountingOnClose: !1,
        }),
        t.context.onOpenChangeComplete?.(!1));
    }),
    a = t.useState("preventUnmountingOnClose");
  return (
    ys({
      enabled: r && !e && !a,
      open: e,
      ref: t.context.popupRef,
      onComplete() {
        e || i();
      },
    }),
    { forceUnmount: i, transitionStatus: o }
  );
}
function qi(e, t) {
  (e.useSyncedValues(t),
    xe(
      () => () => {
        e.update({
          activeTriggerProps: Xe,
          inactiveTriggerProps: Xe,
          popupProps: Xe,
        });
      },
      [e],
    ));
}
function kd(e, t) {
  (xe(() => {
    !t && e.state.openMethod !== null && e.set("openMethod", null);
  }, [t, e]),
    xe(
      () => () => {
        e.state.openMethod !== null && e.set("openMethod", null);
      },
      [e],
    ));
}
class ar {
  constructor() {
    ((this.elementsSet = new Set()), (this.idMap = new Map()));
  }
  add(t, n) {
    const r = this.idMap.get(t);
    r !== n &&
      (r !== void 0 && this.elementsSet.delete(r),
      this.elementsSet.add(n),
      this.idMap.set(t, n));
  }
  delete(t) {
    const n = this.idMap.get(t);
    n && (this.elementsSet.delete(n), this.idMap.delete(t));
  }
  hasElement(t) {
    return this.elementsSet.has(t);
  }
  hasMatchingElement(t) {
    for (const n of this.elementsSet) if (t(n)) return !0;
    return !1;
  }
  getById(t) {
    return this.idMap.get(t);
  }
  entries() {
    return this.idMap.entries();
  }
  elements() {
    return this.elementsSet.values();
  }
  get size() {
    return this.idMap.size;
  }
}
function Ad() {
  return new ir({
    open: !1,
    transitionStatus: void 0,
    floatingElement: null,
    referenceElement: null,
    triggerElements: new ar(),
    floatingId: void 0,
    syncOnly: !1,
    nested: !1,
    onOpenChange: void 0,
  });
}
function Zi() {
  return {
    open: !1,
    openProp: void 0,
    mounted: !1,
    transitionStatus: void 0,
    floatingRootContext: Ad(),
    floatingId: void 0,
    triggerCount: 0,
    preventUnmountingOnClose: !1,
    payload: void 0,
    activeTriggerId: null,
    activeTriggerElement: null,
    triggerIdProp: void 0,
    popupElement: null,
    positionerElement: null,
    activeTriggerProps: Xe,
    inactiveTriggerProps: Xe,
    popupProps: Xe,
  };
}
function Qi(e, t, n = !1) {
  return new ir({
    open: !1,
    transitionStatus: void 0,
    floatingElement: null,
    referenceElement: null,
    triggerElements: e,
    floatingId: t,
    syncOnly: !0,
    nested: n,
    onOpenChange: void 0,
  });
}
const hn = ae((e) => e.triggerIdProp ?? e.activeTriggerId),
  ws = ae((e) => e.openProp ?? e.open),
  xo = ae((e) => (e.popupElement?.id ?? e.floatingId) || void 0);
function Ji(e, t) {
  return t !== void 0 && ws(e) && hn(e) === t;
}
function Od(e, t) {
  return Ji(e, t)
    ? !0
    : t !== void 0 && ws(e) && hn(e) == null && e.triggerCount === 1;
}
const ea = {
  open: ws,
  mounted: ae((e) => e.mounted),
  transitionStatus: ae((e) => e.transitionStatus),
  floatingRootContext: ae((e) => e.floatingRootContext),
  triggerCount: ae((e) => e.triggerCount),
  preventUnmountingOnClose: ae((e) => e.preventUnmountingOnClose),
  payload: ae((e) => e.payload),
  activeTriggerId: hn,
  activeTriggerElement: ae((e) => (e.mounted ? e.activeTriggerElement : null)),
  popupId: xo,
  isTriggerActive: ae((e, t) => t !== void 0 && hn(e) === t),
  isOpenedByTrigger: ae((e, t) => Ji(e, t)),
  isMountedByTrigger: ae((e, t) => t !== void 0 && hn(e) === t && e.mounted),
  triggerProps: ae((e, t) =>
    t ? e.activeTriggerProps : e.inactiveTriggerProps,
  ),
  triggerPopupId: ae((e, t) => (Od(e, t) ? xo(e) : void 0)),
  popupProps: ae((e) => e.popupProps),
  popupElement: ae((e) => e.popupElement),
  positionerElement: ae((e) => e.positionerElement),
};
function jd(e) {
  const { open: t = !1, onOpenChange: n, elements: r = {} } = e,
    s = sr(),
    o = ms() != null,
    i = jt(
      () =>
        new ir({
          open: t,
          transitionStatus: void 0,
          onOpenChange: n,
          referenceElement: r.reference ?? null,
          floatingElement: r.floating ?? null,
          triggerElements: new ar(),
          floatingId: s,
          syncOnly: !1,
          nested: o,
        }),
    ).current;
  return (
    xe(() => {
      const a = { open: t, floatingId: s };
      (r.reference !== void 0 &&
        ((a.referenceElement = r.reference),
        (a.domReferenceElement = he(r.reference) ? r.reference : null)),
        r.floating !== void 0 && (a.floatingElement = r.floating),
        i.update(a));
    }, [t, s, r.reference, r.floating, i]),
    (i.context.onOpenChange = n),
    (i.context.nested = o),
    i
  );
}
function Id(e = {}) {
  const { nodeId: t, externalTree: n } = e,
    r = jd(e),
    s = e.rootContext || r,
    o = s.useState("referenceElement"),
    i = s.useState("floatingElement"),
    a = s.useState("domReferenceElement"),
    f = s.useState("open"),
    u = s.useState("floatingId"),
    [l, d] = m.useState(null),
    [p, g] = m.useState(void 0),
    [h, x] = m.useState(void 0),
    v = m.useRef(null),
    S = yn(n),
    b = m.useMemo(
      () => ({ reference: o, floating: i, domReference: a }),
      [o, i, a],
    ),
    C = nd({ ...e, elements: { ...b, ...(l && { reference: l }) } }),
    w = he(p) ? p : null,
    R = h === void 0 ? s.state.floatingElement : h;
  (s.useSyncedValue("referenceElement", p ?? null),
    s.useSyncedValue("domReferenceElement", p === void 0 ? a : w),
    s.useSyncedValue("floatingElement", R));
  const E = m.useCallback(
      (P) => {
        const I = he(P)
          ? {
              getBoundingClientRect: () => P.getBoundingClientRect(),
              getClientRects: () => P.getClientRects(),
              contextElement: P,
            }
          : P;
        (d(I), C.refs.setReference(I));
      },
      [C.refs],
    ),
    T = m.useCallback(
      (P) => {
        ((he(P) || P === null) && ((v.current = P), g(P)),
          (he(C.refs.reference.current) ||
            C.refs.reference.current === null ||
            (P !== null && !he(P))) &&
            C.refs.setReference(P));
      },
      [C.refs, g],
    ),
    O = m.useCallback(
      (P) => {
        (x(P), C.refs.setFloating(P));
      },
      [C.refs],
    ),
    A = m.useMemo(
      () => ({
        ...C.refs,
        setReference: T,
        setFloating: O,
        setPositionReference: E,
        domReference: v,
      }),
      [C.refs, T, O, E],
    ),
    j = m.useMemo(() => ({ ...C.elements, domReference: a }), [C.elements, a]),
    $ = m.useMemo(
      () => ({
        ...C,
        dataRef: s.context.dataRef,
        open: f,
        onOpenChange: s.setOpen,
        events: s.context.events,
        floatingId: u,
        refs: A,
        elements: j,
        nodeId: t,
        rootStore: s,
      }),
      [C, A, j, t, s, f, u],
    );
  return (
    xe(() => {
      a && (v.current = a);
    }, [a]),
    xe(() => {
      s.context.dataRef.current.floatingContext = $;
      const P = S?.nodesRef.current.find((I) => I.id === t);
      P && (P.context = $);
    }),
    m.useMemo(
      () => ({ ...C, context: $, refs: A, elements: j, rootStore: s }),
      [C, A, j, $, s],
    )
  );
}
const Fr = Xl && ei;
function Nd(e, t = {}) {
  const { enabled: n = !0, delay: r } = t,
    s = "rootStore" in e ? e.rootStore : e,
    { events: o, dataRef: i } = s.context,
    a = m.useRef(!1),
    f = m.useRef(null),
    u = m.useRef(!0),
    l = Lt();
  (m.useEffect(() => {
    const p = s.select("domReferenceElement");
    if (!n) return;
    const g = Ge(p);
    function h() {
      const S = s.select("domReferenceElement");
      !s.select("open") && Le(S) && S === ft(Ie(S)) && (a.current = !0);
    }
    function x() {
      u.current = !0;
    }
    function v() {
      u.current = !1;
    }
    return yt(
      me(g, "blur", h),
      Fr && me(g, "keydown", x, !0),
      Fr && me(g, "pointerdown", v, !0),
    );
  }, [s, n]),
    m.useEffect(() => {
      if (!n) return;
      function p(g) {
        if (g.reason === $n || g.reason === is) {
          const h = s.select("domReferenceElement");
          he(h) && ((f.current = h), (a.current = !0));
        }
      }
      return (
        o.on("openchange", p),
        () => {
          o.off("openchange", p);
        }
      );
    }, [o, n, s]));
  const d = m.useMemo(() => {
    function p() {
      ((a.current = !1), (f.current = null));
    }
    return {
      onMouseLeave() {
        p();
      },
      onFocus(g) {
        const h = g.currentTarget;
        if (a.current) {
          if (f.current === h) return;
          p();
        }
        const x = it(g.nativeEvent);
        if (he(x)) {
          if (Fr && !g.relatedTarget) {
            if (!u.current && !ss(x)) return;
          } else if (!cc(x)) return;
        }
        const v = Hn(g.relatedTarget, s.context.triggerElements),
          { nativeEvent: S, currentTarget: b } = g,
          C = typeof r == "function" ? r() : r;
        if ((s.select("open") && v) || C === 0 || C === void 0) {
          s.setOpen(!0, Be(Mn, S, b));
          return;
        }
        l.start(C, () => {
          a.current || s.setOpen(!0, Be(Mn, S, b));
        });
      },
      onBlur(g) {
        p();
        const h = g.relatedTarget,
          x = g.nativeEvent,
          v =
            he(h) &&
            h.hasAttribute(xn("focus-guard")) &&
            h.getAttribute("data-type") === "outside";
        l.start(0, () => {
          const S = s.select("domReferenceElement"),
            b = ft(Ie(S));
          (!h && b === S) ||
            ie(i.current.floatingContext?.refs.floating.current, b) ||
            ie(S, b) ||
            v ||
            Hn(h ?? b, s.context.triggerElements) ||
            s.setOpen(!1, Be(Mn, x));
        });
      },
    };
  }, [i, r, s, l]);
  return m.useMemo(() => (n ? { reference: d, trigger: d } : {}), [n, d]);
}
class Cs {
  constructor() {
    ((this.pointerType = void 0),
      (this.interactedInside = !1),
      (this.handler = void 0),
      (this.blockMouseMove = !0),
      (this.performedPointerEventsMutation = !1),
      (this.pointerEventsScopeElement = null),
      (this.pointerEventsReferenceElement = null),
      (this.pointerEventsFloatingElement = null),
      (this.restTimeoutPending = !1),
      (this.openChangeTimeout = new pt()),
      (this.restTimeout = new pt()),
      (this.handleCloseOptions = void 0));
  }
  static create() {
    return new Cs();
  }
  dispose = () => {
    (this.openChangeTimeout.clear(), this.restTimeout.clear());
  };
  disposeEffect = () => this.dispose;
}
const qn = new WeakMap();
function Zn(e) {
  if (!e.performedPointerEventsMutation) return;
  const t = e.pointerEventsScopeElement;
  (t &&
    qn.get(t) === e &&
    (e.pointerEventsScopeElement?.style.removeProperty("pointer-events"),
    e.pointerEventsReferenceElement?.style.removeProperty("pointer-events"),
    e.pointerEventsFloatingElement?.style.removeProperty("pointer-events"),
    qn.delete(t)),
    (e.performedPointerEventsMutation = !1),
    (e.pointerEventsScopeElement = null),
    (e.pointerEventsReferenceElement = null),
    (e.pointerEventsFloatingElement = null));
}
function ta(e, t) {
  const { scopeElement: n, referenceElement: r, floatingElement: s } = t,
    o = qn.get(n);
  (o && o !== e && Zn(o),
    Zn(e),
    (e.performedPointerEventsMutation = !0),
    (e.pointerEventsScopeElement = n),
    (e.pointerEventsReferenceElement = r),
    (e.pointerEventsFloatingElement = s),
    qn.set(n, e),
    (n.style.pointerEvents = "none"),
    (r.style.pointerEvents = "auto"),
    (s.style.pointerEvents = "auto"));
}
function Ts(e) {
  const t = e.context.dataRef.current,
    n = jt(() => t.hoverInteractionState ?? Cs.create()).current;
  return (
    t.hoverInteractionState || (t.hoverInteractionState = n),
    ts(t.hoverInteractionState.disposeEffect),
    t.hoverInteractionState
  );
}
function Pd(e, t = {}) {
  const { enabled: n = !0, closeDelay: r = 0, nodeId: s } = t,
    o = "rootStore" in e ? e.rootStore : e,
    i = o.useState("open"),
    a = o.useState("floatingElement"),
    f = o.useState("domReferenceElement"),
    { dataRef: u } = o.context,
    l = yn(),
    d = ms(),
    p = Ts(o),
    g = Lt(),
    h = Te(() => si(u.current.openEvent?.type, p.interactedInside)),
    x = Te(() => dc(u.current.openEvent?.type)),
    v = Te(() => {
      Zn(p);
    });
  (xe(() => {
    i ||
      ((p.pointerType = void 0),
      (p.restTimeoutPending = !1),
      (p.interactedInside = !1),
      v());
  }, [i, p, v]),
    m.useEffect(() => v, [v]),
    xe(() => {
      if (
        n &&
        i &&
        p.handleCloseOptions?.blockPointerEvents &&
        x() &&
        he(f) &&
        a
      ) {
        const S = f,
          b = a,
          C = Ie(a),
          w = l?.nodesRef.current.find((O) => O.id === d)?.context?.elements
            .floating;
        w && (w.style.pointerEvents = "");
        const R =
            p.pointerEventsScopeElement !== b
              ? p.pointerEventsScopeElement
              : null,
          E = w !== b ? w : null,
          T =
            p.handleCloseOptions?.getScope?.() ??
            R ??
            E ??
            S.closest("[data-rootownerid]") ??
            C.body;
        return (
          ta(p, { scopeElement: T, referenceElement: S, floatingElement: b }),
          () => {
            v();
          }
        );
      }
    }, [n, i, f, a, p, x, l, d, v]),
    m.useEffect(() => {
      if (!n) return;
      function S() {
        return !!(l && d && Ft(l.nodesRef.current, d).length > 0);
      }
      function b(O) {
        const A = _n(r, "close", p.pointerType),
          j = () => {
            (o.setOpen(!1, Be(Ze, O)), l?.events.emit("floating.closed", O));
          };
        A
          ? p.openChangeTimeout.start(A, j)
          : (p.openChangeTimeout.clear(), j());
      }
      function C(O) {
        const A = it(O);
        if (!lc(A)) {
          p.interactedInside = !1;
          return;
        }
        p.interactedInside = A?.closest("[aria-haspopup]") != null;
      }
      function w() {
        (p.openChangeTimeout.clear(),
          g.clear(),
          l?.events.off("floating.closed", E),
          v());
      }
      function R(O) {
        if (S() && l) {
          l.events.on("floating.closed", E);
          return;
        }
        if (Hn(O.relatedTarget, o.context.triggerElements)) return;
        const A = u.current.floatingContext?.nodeId ?? s,
          j = O.relatedTarget;
        if (
          !(
            l &&
            A &&
            he(j) &&
            Ft(l.nodesRef.current, A, !1).some((P) =>
              ie(P.context?.elements.floating, j),
            )
          )
        ) {
          if (p.handler) {
            p.handler(O);
            return;
          }
          (v(), h() || b(O));
        }
      }
      function E(O) {
        !l ||
          !d ||
          S() ||
          g.start(0, () => {
            (l.events.off("floating.closed", E),
              o.setOpen(!1, Be(Ze, O)),
              l.events.emit("floating.closed", O));
          });
      }
      const T = a;
      return yt(
        T && me(T, "mouseenter", w),
        T && me(T, "mouseleave", R),
        T && me(T, "pointerdown", C, !0),
        () => {
          l?.events.off("floating.closed", E);
        },
      );
    }, [n, a, o, u, r, s, h, v, p, l, d, g]));
}
const Bd = { current: null };
function Md(e, t = {}) {
  const {
      enabled: n = !0,
      delay: r = 0,
      handleClose: s = null,
      mouseOnly: o = !1,
      restMs: i = 0,
      move: a = !0,
      triggerElementRef: f = Bd,
      externalTree: u,
      isActiveTrigger: l = !0,
      getHandleCloseContext: d,
      isClosing: p,
      shouldOpen: g,
    } = t,
    h = "rootStore" in e ? e.rootStore : e,
    { dataRef: x, events: v } = h.context,
    S = yn(u),
    b = Ts(h),
    C = m.useRef(!1),
    w = et(s),
    R = et(r),
    E = et(i),
    T = et(n),
    O = et(g),
    A = et(p),
    j = Te(() => si(x.current.openEvent?.type, b.interactedInside)),
    $ = Te(() => O.current?.() !== !1),
    P = Te((k, M, H) => {
      const N = h.context.triggerElements;
      if (N.hasElement(M)) return !k || !ie(k, M);
      if (!he(H)) return !1;
      const D = H;
      return N.hasMatchingElement((U) => ie(U, D)) && (!k || !ie(k, D));
    }),
    I = Te(() => {
      if (!b.handler) return;
      (Ie(h.select("domReferenceElement")).removeEventListener(
        "mousemove",
        b.handler,
      ),
        (b.handler = void 0));
    }),
    L = Te(() => {
      Zn(b);
    });
  return (
    l && (b.handleCloseOptions = w.current?.__options),
    m.useEffect(() => I, [I]),
    m.useEffect(() => {
      if (!n) return;
      function k(M) {
        M.open
          ? (C.current = !1)
          : ((C.current = M.reason === Ze),
            I(),
            b.openChangeTimeout.clear(),
            b.restTimeout.clear(),
            (b.blockMouseMove = !0),
            (b.restTimeoutPending = !1));
      }
      return (
        v.on("openchange", k),
        () => {
          v.off("openchange", k);
        }
      );
    }, [n, v, b, I]),
    m.useEffect(() => {
      if (!n) return;
      function k(D, U = !0) {
        const Q = _n(R.current, "close", b.pointerType);
        Q
          ? b.openChangeTimeout.start(Q, () => {
              (h.setOpen(!1, Be(Ze, D)), S?.events.emit("floating.closed", D));
            })
          : U &&
            (b.openChangeTimeout.clear(),
            h.setOpen(!1, Be(Ze, D)),
            S?.events.emit("floating.closed", D));
      }
      const M = f.current ?? (l ? h.select("domReferenceElement") : null);
      if (!he(M)) return;
      function H(D) {
        if (
          (b.openChangeTimeout.clear(),
          (b.blockMouseMove = !1),
          o && !mn(b.pointerType))
        )
          return;
        const U = Us(E.current),
          Q = _n(R.current, "open", b.pointerType),
          ve = it(D),
          Y = D.currentTarget ?? null,
          J = h.select("domReferenceElement");
        let ce = Y;
        if (he(ve) && !h.context.triggerElements.hasElement(ve)) {
          for (const ne of h.context.triggerElements.elements())
            if (ie(ne, ve)) {
              ce = ne;
              break;
            }
        }
        he(Y) &&
          he(J) &&
          !h.context.triggerElements.hasElement(Y) &&
          ie(Y, J) &&
          (ce = J);
        const z = ce == null ? !1 : P(J, ce, ve),
          ue = h.select("open"),
          X = A.current?.() ?? h.select("transitionStatus") === "ending",
          te = !ue && X && C.current,
          ye = !z && he(ce) && he(J) && ie(J, ce) && te,
          W = U > 0 && !Q,
          B = (z && (ue || te)) || ye,
          G = !ue || z;
        if (B) {
          $() && h.setOpen(!0, Be(Ze, D, ce));
          return;
        }
        W ||
          (Q
            ? b.openChangeTimeout.start(Q, () => {
                G && $() && h.setOpen(!0, Be(Ze, D, ce));
              })
            : G && $() && h.setOpen(!0, Be(Ze, D, ce)));
      }
      function N(D) {
        if (j()) {
          L();
          return;
        }
        I();
        const U = h.select("domReferenceElement"),
          Q = Ie(U);
        (b.restTimeout.clear(), (b.restTimeoutPending = !1));
        const ve = x.current.floatingContext ?? d?.();
        if (Hn(D.relatedTarget, h.context.triggerElements)) return;
        if (w.current && ve) {
          h.select("open") || b.openChangeTimeout.clear();
          const J = f.current;
          ((b.handler = w.current({
            ...ve,
            tree: S,
            x: D.clientX,
            y: D.clientY,
            onClose() {
              (L(),
                I(),
                T.current &&
                  !j() &&
                  J === h.select("domReferenceElement") &&
                  k(D, !0));
            },
          })),
            Q.addEventListener("mousemove", b.handler),
            b.handler(D));
          return;
        }
        (b.pointerType !== "touch" ||
          !ie(h.select("floatingElement"), D.relatedTarget)) &&
          k(D);
      }
      return a
        ? yt(
            me(M, "mousemove", H, { once: !0 }),
            me(M, "mouseenter", H),
            me(M, "mouseleave", N),
          )
        : yt(me(M, "mouseenter", H), me(M, "mouseleave", N));
    }, [I, L, x, R, h, n, w, b, l, P, j, o, a, E, f, S, T, d, A, $]),
    m.useMemo(() => {
      if (!n) return;
      function k(M) {
        b.pointerType = M.pointerType;
      }
      return {
        onPointerDown: k,
        onPointerEnter: k,
        onMouseMove(M) {
          const { nativeEvent: H } = M,
            N = M.currentTarget,
            D = h.select("domReferenceElement"),
            U = h.select("open"),
            Q = P(D, N, M.target);
          if (o && !mn(b.pointerType)) return;
          if (U && Q && b.handleCloseOptions?.blockPointerEvents) {
            const J = h.select("floatingElement");
            if (J) {
              const ce =
                b.handleCloseOptions?.getScope?.() ?? N.ownerDocument.body;
              ta(b, {
                scopeElement: ce,
                referenceElement: N,
                floatingElement: J,
              });
            }
          }
          const ve = Us(E.current);
          if (
            (U && !Q) ||
            ve === 0 ||
            (!Q &&
              b.restTimeoutPending &&
              M.movementX ** 2 + M.movementY ** 2 < 2)
          )
            return;
          b.restTimeout.clear();
          function Y() {
            if (((b.restTimeoutPending = !1), j())) return;
            const J = h.select("open");
            !b.blockMouseMove &&
              (!J || Q) &&
              $() &&
              h.setOpen(!0, Be(Ze, H, N));
          }
          b.pointerType === "touch"
            ? zt.flushSync(() => {
                Y();
              })
            : Q && U
              ? Y()
              : ((b.restTimeoutPending = !0), b.restTimeout.start(ve, Y));
        },
      };
    }, [n, b, j, P, o, h, E, $])
  );
}
const bo = 0.1,
  Dd = bo * bo,
  Ae = 0.5;
function Nn(e, t, n, r, s, o) {
  return r >= t != o >= t && e <= ((s - n) * (t - r)) / (o - r) + n;
}
function Pn(e, t, n, r, s, o, i, a, f, u) {
  let l = !1;
  return (
    Nn(e, t, n, r, s, o) && (l = !l),
    Nn(e, t, s, o, i, a) && (l = !l),
    Nn(e, t, i, a, f, u) && (l = !l),
    Nn(e, t, f, u, n, r) && (l = !l),
    l
  );
}
function Ld(e, t, n) {
  return e >= n.x && e <= n.x + n.width && t >= n.y && t <= n.y + n.height;
}
function Bn(e, t, n, r, s, o) {
  const i = Math.min(n, s),
    a = Math.max(n, s),
    f = Math.min(r, o),
    u = Math.max(r, o);
  return e >= i && e <= a && t >= f && t <= u;
}
function Fd(e = {}) {
  const { blockPointerEvents: t = !1 } = e,
    n = new pt(),
    r = ({
      x: s,
      y: o,
      placement: i,
      elements: a,
      onClose: f,
      nodeId: u,
      tree: l,
    }) => {
      const d = i?.split("-")[0];
      let p = !1,
        g = null,
        h = null,
        x = typeof performance < "u" ? performance.now() : 0;
      function v(b, C) {
        const w = performance.now(),
          R = w - x;
        if (g === null || h === null || R === 0)
          return ((g = b), (h = C), (x = w), !1);
        const E = b - g,
          T = C - h,
          O = E * E + T * T,
          A = R * R * Dd;
        return ((g = b), (h = C), (x = w), O < A);
      }
      function S() {
        (n.clear(), f());
      }
      return function (C) {
        n.clear();
        const w = a.domReference,
          R = a.floating;
        if (!w || !R || d == null || s == null || o == null) return;
        const { clientX: E, clientY: T } = C,
          O = it(C),
          A = C.type === "mouseleave",
          j = ie(R, O),
          $ = ie(w, O);
        if (j && ((p = !0), !A)) return;
        if ($ && ((p = !1), !A)) {
          p = !0;
          return;
        }
        if (A && he(C.relatedTarget) && ie(R, C.relatedTarget)) return;
        function P() {
          return !!(l && Ft(l.nodesRef.current, u).length > 0);
        }
        function I() {
          P() || S();
        }
        if (P()) return;
        const L = w.getBoundingClientRect(),
          k = R.getBoundingClientRect(),
          M = s > k.right - k.width / 2,
          H = o > k.bottom - k.height / 2,
          N = k.width > L.width,
          D = k.height > L.height,
          U = (N ? L : k).left,
          Q = (N ? L : k).right,
          ve = (D ? L : k).top,
          Y = (D ? L : k).bottom;
        if (
          (d === "top" && o >= L.bottom - 1) ||
          (d === "bottom" && o <= L.top + 1) ||
          (d === "left" && s >= L.right - 1) ||
          (d === "right" && s <= L.left + 1)
        ) {
          I();
          return;
        }
        let J = !1;
        switch (d) {
          case "top":
            J = Bn(E, T, U, L.top + 1, Q, k.bottom - 1);
            break;
          case "bottom":
            J = Bn(E, T, U, k.top + 1, Q, L.bottom - 1);
            break;
          case "left":
            J = Bn(E, T, k.right - 1, Y, L.left + 1, ve);
            break;
          case "right":
            J = Bn(E, T, L.right - 1, Y, k.left + 1, ve);
            break;
        }
        if (J) return;
        if (p && !Ld(E, T, L)) {
          I();
          return;
        }
        if (!A && v(E, T)) {
          I();
          return;
        }
        let ce = !1;
        switch (d) {
          case "top": {
            const z = N ? Ae / 2 : Ae * 4,
              ue = N || M ? s + z : s - z,
              X = N ? s - z : M ? s + z : s - z,
              te = o + Ae + 1,
              ye = M || N ? k.bottom - Ae : k.top,
              W = M ? (N ? k.bottom - Ae : k.top) : k.bottom - Ae;
            ce = Pn(E, T, ue, te, X, te, k.left, ye, k.right, W);
            break;
          }
          case "bottom": {
            const z = N ? Ae / 2 : Ae * 4,
              ue = N || M ? s + z : s - z,
              X = N ? s - z : M ? s + z : s - z,
              te = o - Ae,
              ye = M || N ? k.top + Ae : k.bottom,
              W = M ? (N ? k.top + Ae : k.bottom) : k.top + Ae;
            ce = Pn(E, T, ue, te, X, te, k.left, ye, k.right, W);
            break;
          }
          case "left": {
            const z = D ? Ae / 2 : Ae * 4,
              ue = D || H ? o + z : o - z,
              X = D ? o - z : H ? o + z : o - z,
              te = s + Ae + 1,
              ye = H || D ? k.right - Ae : k.left,
              W = H ? (D ? k.right - Ae : k.left) : k.right - Ae;
            ce = Pn(E, T, ye, k.top, W, k.bottom, te, ue, te, X);
            break;
          }
          case "right": {
            const z = D ? Ae / 2 : Ae * 4,
              ue = D || H ? o + z : o - z,
              X = D ? o - z : H ? o + z : o - z,
              te = s - Ae,
              ye = H || D ? k.left + Ae : k.right,
              W = H ? (D ? k.left + Ae : k.right) : k.left + Ae;
            ce = Pn(E, T, te, ue, te, X, ye, k.top, W, k.bottom);
            break;
          }
        }
        ce ? p || n.start(40, I) : I();
      };
    };
  return ((r.__options = { ...e, blockPointerEvents: t }), r);
}
const Hd = {
  ...ea,
  disabled: ae((e) => e.disabled),
  instantType: ae((e) => e.instantType),
  isInstantPhase: ae((e) => e.isInstantPhase),
  trackCursorAxis: ae((e) => e.trackCursorAxis),
  disableHoverablePopup: ae((e) => e.disableHoverablePopup),
  lastOpenChangeReason: ae((e) => e.openChangeReason),
  closeOnClick: ae((e) => e.closeOnClick),
  closeDelay: ae((e) => e.closeDelay),
  hasViewport: ae((e) => e.hasViewport),
};
class Es extends bs {
  constructor(t, n, r = !1) {
    const s = new ar(),
      o = { ..._d(), ...t };
    ((o.floatingRootContext = Qi(s, n, r)),
      super(
        o,
        {
          popupRef: m.createRef(),
          onOpenChange: void 0,
          onOpenChangeComplete: void 0,
          triggerElements: s,
        },
        Hd,
      ));
  }
  setOpen = (t, n) => {
    const r = n.reason,
      s = r === Ze,
      o = t && r === Mn,
      i = !t && (r === $n || r === is);
    if (
      ((n.preventUnmountOnClose = () => {
        this.set("preventUnmountingOnClose", !0);
      }),
      this.context.onOpenChange?.(t, n),
      n.isCanceled)
    )
      return;
    this.state.floatingRootContext.dispatchOpenChange(t, n);
    const a = () => {
      const f = { open: t, openChangeReason: r };
      (o
        ? (f.instantType = "focus")
        : i
          ? (f.instantType = "dismiss")
          : r === Ze && (f.instantType = void 0),
        Yi(f, t, n.trigger),
        this.update(f));
    };
    s ? zt.flushSync(a) : a();
  };
  cancelPendingOpen(t) {
    this.state.floatingRootContext.dispatchOpenChange(!1, Be($n, t));
  }
  static useStore(t, n) {
    return Vi(t, (s, o) => new Es(n, s, o)).store;
  }
}
function _d() {
  return {
    ...Zi(),
    disabled: !1,
    instantType: void 0,
    isInstantPhase: !1,
    trackCursorAxis: "none",
    disableHoverablePopup: !1,
    openChangeReason: null,
    closeOnClick: !0,
    closeDelay: 0,
    hasViewport: !1,
  };
}
const $d = Xo(function (t) {
  const {
      disabled: n = !1,
      defaultOpen: r = !1,
      open: s,
      disableHoverablePopup: o = !1,
      trackCursorAxis: i = "none",
      actionsRef: a,
      onOpenChange: f,
      onOpenChangeComplete: u,
      handle: l,
      triggerId: d,
      defaultTriggerId: p = null,
      children: g,
    } = t,
    h = Es.useStore(l?.store, {
      open: r,
      openProp: s,
      activeTriggerId: p,
      triggerIdProp: d,
    });
  (zo(() => {
    s === void 0 &&
      h.state.open === !1 &&
      r === !0 &&
      h.update({ open: !0, activeTriggerId: p });
  }),
    h.useControlledProp("openProp", s),
    h.useControlledProp("triggerIdProp", d),
    h.useContextCallback("onOpenChange", f),
    h.useContextCallback("onOpenChangeComplete", u));
  const x = h.useState("open"),
    v = !n && x,
    S = h.useState("activeTriggerId"),
    b = h.useState("mounted"),
    C = h.useState("payload");
  (h.useSyncedValues({ trackCursorAxis: i, disableHoverablePopup: o }),
    h.useSyncedValue("disabled", n),
    Xi(h));
  const { forceUnmount: w, transitionStatus: R } = zi(v, h),
    E = h.useState("isInstantPhase"),
    T = h.useState("instantType"),
    O = h.useState("lastOpenChangeReason"),
    A = m.useRef(null);
  (xe(() => {
    x && n && h.setOpen(!1, Be(pc));
  }, [x, n, h]),
    xe(() => {
      (R === "ending" && O === oi) || (R !== "ending" && E)
        ? (T !== "delay" && (A.current = T), h.set("instantType", "delay"))
        : A.current !== null &&
          (h.set("instantType", A.current), (A.current = null));
    }, [R, E, O, T, h]),
    xe(() => {
      v && S == null && h.set("payload", void 0);
    }, [h, S, v]));
  const j = m.useCallback(() => {
    h.setOpen(!1, Be(li));
  }, [h]);
  m.useImperativeHandle(a, () => ({ unmount: w, close: j }), [w, j]);
  const $ = v || b || (!n && i !== "none");
  return c.jsxs(qo.Provider, {
    value: h,
    children: [
      $ && c.jsx(Gd, { store: h, disabled: n, trackCursorAxis: i }),
      typeof g == "function" ? g({ payload: C }) : g,
    ],
  });
});
function Gd({ store: e, disabled: t, trackCursorAxis: n }) {
  const r = e.useState("floatingRootContext"),
    s = Bi(r, { enabled: !t, referencePress: () => e.select("closeOnClick") }),
    o = bu(r, { enabled: !t && n !== "none", axis: n === "none" ? void 0 : n }),
    i = m.useMemo(
      () => Yt(o.reference, s.reference),
      [o.reference, s.reference],
    ),
    a = m.useMemo(() => Yt(o.trigger, s.trigger), [o.trigger, s.trigger]),
    f = m.useMemo(
      () => Yt(Ss, o.floating, s.floating),
      [o.floating, s.floating],
    );
  return (
    qi(e, { activeTriggerProps: i, inactiveTriggerProps: a, popupProps: f }),
    null
  );
}
let Vt = (function (e) {
    return (
      (e.open = "data-open"),
      (e.closed = "data-closed"),
      (e[(e.startingStyle = bn.startingStyle)] = "startingStyle"),
      (e[(e.endingStyle = bn.endingStyle)] = "endingStyle"),
      (e.anchorHidden = "data-anchor-hidden"),
      (e.side = "data-side"),
      (e.align = "data-align"),
      e
    );
  })({}),
  na = (function (e) {
    return ((e.popupOpen = "data-popup-open"), (e.pressed = "data-pressed"), e);
  })({});
const Ud = { [na.popupOpen]: "" },
  Wd = { [Vt.open]: "" },
  Kd = { [Vt.closed]: "" },
  Vd = { [Vt.anchorHidden]: "" },
  Yd = {
    open(e) {
      return e ? Ud : null;
    },
  },
  Sn = {
    open(e) {
      return e ? Wd : Kd;
    },
    anchorHidden(e) {
      return e ? Vd : null;
    },
  };
function ra(e) {
  return sr(e, "base-ui");
}
const sa = m.createContext(void 0);
function Xd() {
  return m.useContext(sa);
}
let zd = (function (e) {
  return (
    (e[(e.popupOpen = na.popupOpen)] = "popupOpen"),
    (e.triggerDisabled = "data-trigger-disabled"),
    e
  );
})({});
const qd = 600,
  oa = "data-base-ui-tooltip-trigger";
function vo(e) {
  if ("composedPath" in e) {
    const n = e.composedPath();
    for (let r = 0; r < n.length; r += 1) {
      const s = n[r];
      if (he(s)) return s;
    }
  }
  const t = e.target;
  return he(t) ? t : null;
}
function Zd(e) {
  let t = e;
  for (; t; ) {
    if (t.hasAttribute(oa)) return t;
    const n = t.parentElement;
    if (n) {
      t = n;
      continue;
    }
    const r = t.getRootNode();
    t = "host" in r && he(r.host) ? r.host : null;
  }
  return null;
}
const Qd = Gl(function (t, n) {
    const {
        render: r,
        className: s,
        style: o,
        handle: i,
        payload: a,
        disabled: f,
        delay: u,
        closeOnClick: l = !0,
        closeDelay: d,
        id: p,
        ...g
      } = t,
      h = vn(!0),
      x = i?.store ?? h;
    if (!x) throw new Error(It(82));
    const v = ra(p),
      S = x.useState("isTriggerActive", v),
      b = x.useState("isOpenedByTrigger", v),
      C = x.useState("floatingRootContext"),
      w = m.useRef(null),
      R = u ?? qd,
      E = d ?? 0,
      { registerTrigger: T, isMountedByThisTrigger: O } = Rd(v, w, x, {
        payload: a,
        closeOnClick: l,
        closeDelay: E,
      }),
      A = Xd(),
      { delayRef: j, isInstantPhase: $, hasProvider: P } = mc(C, { open: b }),
      I = Ts(C);
    x.useSyncedValue("isInstantPhase", $);
    const L = x.useState("disabled"),
      k = f ?? L,
      M = et(k),
      H = x.useState("trackCursorAxis"),
      N = x.useState("disableHoverablePopup"),
      D = m.useRef(!1),
      U = Lt(),
      Q = m.useRef(void 0);
    function ve() {
      const B = A?.delay,
        G = typeof j.current == "object" ? j.current.open : void 0;
      let ne = R;
      return (P && (G !== 0 ? (ne = u ?? B ?? R) : (ne = 0)), ne);
    }
    function Y(B) {
      const G = w.current;
      if (!G || !B) return !1;
      const ne = Zd(B);
      return ne !== null && ne !== G && ie(G, ne);
    }
    function J(B) {
      const G = Y(B);
      return (
        (D.current = G),
        G &&
          (I.openChangeTimeout.clear(),
          I.restTimeout.clear(),
          (I.restTimeoutPending = !1),
          U.clear()),
        G
      );
    }
    const ce = Md(C, {
        enabled: !k,
        mouseOnly: !0,
        move: !1,
        handleClose: !N && H !== "both" ? Fd() : null,
        restMs: ve,
        delay() {
          const B = typeof j.current == "object" ? j.current.close : void 0;
          let G = E;
          return (d == null && P && (G = B), { close: G });
        },
        triggerElementRef: w,
        isActiveTrigger: S,
        isClosing: () => x.select("transitionStatus") === "ending",
        shouldOpen() {
          return !D.current;
        },
      }),
      z = Nd(C, { enabled: !k }).reference,
      ue = (B) => {
        const G = D.current,
          ne = vo(B),
          de = J(ne),
          se = w.current,
          q = se && ne && ie(se, ne);
        if (de && x.select("open") && x.select("lastOpenChangeReason") === Ze) {
          x.setOpen(!1, Be(Ze, B));
          return;
        }
        if (
          G &&
          !de &&
          q &&
          !M.current &&
          !x.select("open") &&
          se &&
          mn(Q.current)
        ) {
          const be = () => {
              !D.current &&
                !M.current &&
                !x.select("open") &&
                x.setOpen(!0, Be(Ze, B, se));
            },
            ee = ve();
          ee === 0 ? (U.clear(), be()) : U.start(ee, be);
        }
      },
      X = x.useState("triggerProps", O);
    return Nt("button", t, {
      state: { open: b },
      ref: [n, T, w],
      props: [
        ce,
        z,
        O || H !== "none" ? X : void 0,
        {
          onMouseOver(B) {
            ue(B.nativeEvent);
          },
          onFocus(B) {
            Y(vo(B.nativeEvent)) && B.preventBaseUIHandler();
          },
          onMouseLeave() {
            ((D.current = !1), U.clear(), (Q.current = void 0));
          },
          onPointerEnter(B) {
            Q.current = B.pointerType;
          },
          onPointerDown(B) {
            ((Q.current = B.pointerType),
              x.set("closeOnClick", l),
              l && !x.select("open") && x.cancelPendingOpen(B.nativeEvent));
          },
          onClick(B) {
            l && !x.select("open") && x.cancelPendingOpen(B.nativeEvent);
          },
          id: v,
          [zd.triggerDisabled]: k ? "" : void 0,
          [oa]: k ? void 0 : "",
        },
        g,
      ],
      stateAttributesMapping: Yd,
    });
  }),
  ia = m.createContext(void 0);
function Jd() {
  const e = m.useContext(ia);
  if (e === void 0) throw new Error(It(70));
  return e;
}
const ef = m.forwardRef(function (t, n) {
    const {
        children: r,
        container: s,
        className: o,
        render: i,
        style: a,
        ...f
      } = t,
      { portalNode: u, portalSubtree: l } = Pi({
        container: s,
        ref: n,
        componentProps: t,
        elementProps: f,
      });
    return !l && !u
      ? null
      : c.jsxs(m.Fragment, { children: [l, u && zt.createPortal(r, u)] });
  }),
  tf = m.forwardRef(function (t, n) {
    const { keepMounted: r = !1, ...s } = t;
    return vn().useState("mounted") || r
      ? c.jsx(ia.Provider, { value: r, children: c.jsx(ef, { ref: n, ...s }) })
      : null;
  }),
  aa = m.createContext(void 0);
function la() {
  const e = m.useContext(aa);
  if (e === void 0) throw new Error(It(71));
  return e;
}
const nf = m.createContext(void 0);
function rf() {
  return m.useContext(nf)?.direction ?? "ltr";
}
const sf = (e) => ({
    name: "arrow",
    options: e,
    async fn(t) {
      const {
          x: n,
          y: r,
          placement: s,
          rects: o,
          platform: i,
          elements: a,
          middlewareData: f,
        } = t,
        {
          element: u,
          padding: l = 0,
          offsetParent: d = "real",
        } = Ot(e, t) || {};
      if (u == null) return {};
      const p = pi(l),
        g = { x: n, y: r },
        h = us(s),
        x = cs(h),
        v = await i.getDimensions(u),
        S = h === "y",
        b = S ? "top" : "left",
        C = S ? "bottom" : "right",
        w = S ? "clientHeight" : "clientWidth",
        R = o.reference[x] + o.reference[h] - g[h] - o.floating[x],
        E = g[h] - o.reference[h],
        T = d === "real" ? await i.getOffsetParent?.(u) : a.floating;
      let O = a.floating[w] || o.floating[x];
      (!O || !(await i.isElement?.(T))) && (O = a.floating[w] || o.floating[x]);
      const A = R / 2 - E / 2,
        j = O / 2 - v[x] / 2 - 1,
        $ = Math.min(p[b], j),
        P = Math.min(p[C], j),
        I = $,
        L = O - v[x] - P,
        k = O / 2 - v[x] / 2 + A,
        M = Vr(I, k, L),
        H =
          !f.arrow &&
          _t(s) != null &&
          k !== M &&
          o.reference[x] / 2 - (k < I ? $ : P) - v[x] / 2 < 0,
        N = H ? (k < I ? k - I : k - L) : 0;
      return {
        [h]: g[h] + N,
        data: {
          [h]: M,
          centerOffset: k - M - N,
          ...(H && { alignmentOffset: N }),
        },
        reset: H,
      };
    },
  }),
  of = (e, t) => ({ ...sf(e), options: [e, t] }),
  af = {
    name: "hide",
    async fn(e) {
      const { width: t, height: n, x: r, y: s } = e.rects.reference,
        o = t === 0 && n === 0 && r === 0 && s === 0;
      return {
        data: {
          referenceHidden: (await ld().fn(e)).data?.referenceHidden || o,
        },
      };
    },
  },
  Fn = { sideX: "left", sideY: "top" },
  lf = {
    name: "adaptiveOrigin",
    async fn(e) {
      const {
          x: t,
          y: n,
          rects: { floating: r },
          elements: { floating: s },
          platform: o,
          strategy: i,
          placement: a,
        } = e,
        f = Ge(s),
        u = f.getComputedStyle(s);
      if (!(u.transitionDuration !== "0s" && u.transitionDuration !== ""))
        return { x: t, y: n, data: Fn };
      const d = await o.getOffsetParent?.(s);
      let p = { width: 0, height: 0 };
      if (i === "fixed" && f?.visualViewport)
        p = { width: f.visualViewport.width, height: f.visualViewport.height };
      else if (d === f) {
        const b = Ie(s);
        p = {
          width: b.documentElement.clientWidth,
          height: b.documentElement.clientHeight,
        };
      } else (await o.isElement?.(d)) && (p = await o.getDimensions(d));
      const g = tt(a);
      let h = t,
        x = n;
      (g === "left" && (h = p.width - (t + r.width)),
        g === "top" && (x = p.height - (n + r.height)));
      const v = g === "left" ? "right" : Fn.sideX,
        S = g === "top" ? "bottom" : Fn.sideY;
      return { x: h, y: x, data: { sideX: v, sideY: S } };
    },
  };
function ca(e, t, n) {
  const r = e === "inline-start" || e === "inline-end";
  return {
    top: "top",
    right: r ? (n ? "inline-start" : "inline-end") : "right",
    bottom: "bottom",
    left: r ? (n ? "inline-end" : "inline-start") : "left",
  }[t];
}
function yo(e, t, n) {
  const { rects: r, placement: s } = e;
  return {
    side: ca(t, tt(s), n),
    align: _t(s) || "center",
    anchor: { width: r.reference.width, height: r.reference.height },
    positioner: { width: r.floating.width, height: r.floating.height },
  };
}
function cf(e) {
  const {
      anchor: t,
      positionMethod: n = "absolute",
      side: r = "bottom",
      sideOffset: s = 0,
      align: o = "center",
      alignOffset: i = 0,
      collisionBoundary: a,
      collisionPadding: f = 5,
      sticky: u = !1,
      arrowPadding: l = 5,
      disableAnchorTracking: d = !1,
      inline: p,
      keepMounted: g = !1,
      floatingRootContext: h,
      mounted: x,
      collisionAvoidance: v,
      shiftCrossAxis: S = !1,
      nodeId: b,
      adaptiveOrigin: C,
      lazyFlip: w = !1,
      externalTree: R,
    } = e,
    [E, T] = m.useState(null);
  !x && E !== null && T(null);
  const O = v.side || "flip",
    A = v.align || "flip",
    j = v.fallbackAxisSide || "end",
    $ = typeof t == "function" ? t : void 0,
    P = Te($),
    I = $ ? P : t,
    L = et(t),
    k = et(x),
    H = rf() === "rtl",
    N =
      E ||
      {
        top: "top",
        right: "right",
        bottom: "bottom",
        left: "left",
        "inline-end": H ? "left" : "right",
        "inline-start": H ? "right" : "left",
      }[r],
    D = o === "center" ? N : `${N}-${o}`;
  let U = f;
  const Q = 1,
    ve = r === "bottom" ? Q : 0,
    Y = r === "top" ? Q : 0,
    J = r === "right" ? Q : 0,
    ce = r === "left" ? Q : 0;
  typeof U == "number"
    ? (U = { top: U + ve, right: U + ce, bottom: U + Y, left: U + J })
    : U &&
      (U = {
        top: (U.top || 0) + ve,
        right: (U.right || 0) + ce,
        bottom: (U.bottom || 0) + Y,
        left: (U.left || 0) + J,
      });
  const z = {
      boundary: a === "clipping-ancestors" ? "clippingAncestors" : a,
      padding: U,
    },
    ue = m.useRef(null),
    X = et(s),
    te = et(i),
    ye = typeof s != "function" ? s : 0,
    W = typeof i != "function" ? i : 0,
    B = [];
  (p && B.push(p),
    B.push(
      rd(
        (pe) => {
          const Pe = yo(pe, r, H),
            Se = typeof X.current == "function" ? X.current(Pe) : X.current,
            He = typeof te.current == "function" ? te.current(Pe) : te.current;
          return { mainAxis: Se, crossAxis: He, alignmentAxis: He };
        },
        [ye, W, H, r],
      ),
    ));
  const G = A === "none" && O !== "shift",
    ne = !G && (u || S || O === "shift"),
    de =
      O === "none"
        ? null
        : id({
            ...z,
            padding: {
              top: U.top + Q,
              right: U.right + Q,
              bottom: U.bottom + Q,
              left: U.left + Q,
            },
            mainAxis: !S && O === "flip",
            crossAxis: A === "flip" ? "alignment" : !1,
            fallbackAxisSideDirection: j,
          }),
    se = G
      ? null
      : sd(
          (pe) => {
            const Pe = Ie(pe.elements.floating).documentElement;
            return {
              ...z,
              rootBoundary: S
                ? { x: 0, y: 0, width: Pe.clientWidth, height: Pe.clientHeight }
                : void 0,
              mainAxis: A !== "none",
              crossAxis: ne,
              limiter:
                u || S
                  ? void 0
                  : od((Se) => {
                      if (!ue.current) return {};
                      const { width: He, height: De } =
                          ue.current.getBoundingClientRect(),
                        Je = lt(tt(Se.placement)),
                        ht = Je === "y" ? He : De,
                        mt = Je === "y" ? U.left + U.right : U.top + U.bottom;
                      return { offset: ht / 2 + mt / 2 };
                    }),
            };
          },
          [z, u, S, U, A],
        );
  (O === "shift" || A === "shift" || o === "center"
    ? B.push(se, de)
    : B.push(de, se),
    B.push(
      ad({
        ...z,
        apply({
          elements: { floating: pe },
          availableWidth: Pe,
          availableHeight: Se,
          rects: He,
        }) {
          if (!k.current) return;
          const De = pe.style;
          (De.setProperty("--available-width", `${Pe}px`),
            De.setProperty("--available-height", `${Se}px`));
          const Je = Ge(pe).devicePixelRatio || 1,
            { x: ht, y: mt, width: $t, height: Gt } = He.reference,
            Bt = (Math.round((ht + $t) * Je) - Math.round(ht * Je)) / Je,
            Mt = (Math.round((mt + Gt) * Je) - Math.round(mt * Je)) / Je;
          (De.setProperty("--anchor-width", `${Bt}px`),
            De.setProperty("--anchor-height", `${Mt}px`));
        },
      }),
      of(
        (pe) => ({
          element: ue.current || Ie(pe.elements.floating).createElement("div"),
          padding: l,
          offsetParent: "floating",
        }),
        [l],
      ),
      {
        name: "transformOrigin",
        fn(pe) {
          const {
              elements: Pe,
              middlewareData: Se,
              placement: He,
              rects: De,
              y: Je,
            } = pe,
            ht = tt(He),
            mt = lt(ht),
            $t = ue.current,
            Gt = Se.arrow?.x || 0,
            Bt = Se.arrow?.y || 0,
            Mt = $t?.clientWidth || 0,
            wn = $t?.clientHeight || 0,
            ln = Gt + Mt / 2,
            Ct = Bt + wn / 2,
            qt = Math.abs(Se.shift?.y || 0),
            Cn = De.reference.height / 2,
            gt = typeof s == "function" ? s(yo(pe, r, H)) : s,
            Zt = qt > gt,
            Tn = {
              top: `${ln}px calc(100% + ${gt}px)`,
              bottom: `${ln}px ${-gt}px`,
              left: `calc(100% + ${gt}px) ${Ct}px`,
              right: `${-gt}px ${Ct}px`,
            }[ht],
            lr = `${ln}px ${De.reference.y + Cn - Je}px`;
          return (
            Pe.floating.style.setProperty(
              "--transform-origin",
              ne && mt === "y" && Zt ? lr : Tn,
            ),
            {}
          );
        },
      },
      af,
      C,
    ),
    xe(() => {
      !x &&
        h &&
        h.update({
          referenceElement: null,
          floatingElement: null,
          domReferenceElement: null,
          positionReference: null,
        });
    }, [x, h]));
  const q = m.useMemo(
      () => ({
        elementResize: !d && typeof ResizeObserver < "u",
        layoutShift: !d && typeof IntersectionObserver < "u",
      }),
      [d],
    ),
    {
      refs: be,
      elements: ee,
      x: Ne,
      y: Me,
      middlewareData: _e,
      update: Re,
      placement: Ve,
      context: F,
      isPositioned: K,
      floatingStyles: oe,
    } = Id({
      rootContext: h,
      open: g ? x : void 0,
      placement: D,
      middleware: B,
      strategy: n,
      whileElementsMounted: g ? void 0 : (...pe) => uo(...pe, q),
      nodeId: b,
      externalTree: R,
    }),
    { sideX: je, sideY: Fe } = _e.adaptiveOrigin || Fn,
    ct = K ? n : "fixed",
    le = m.useMemo(() => {
      const pe = C
        ? { position: ct, [je]: Ne, [Fe]: Me }
        : { position: ct, ...oe };
      return (K || (pe.opacity = 0), pe);
    }, [C, ct, je, Ne, Fe, Me, oe, K]),
    fe = m.useRef(null);
  (xe(() => {
    if (!x) return;
    const pe = L.current,
      Pe = typeof pe == "function" ? pe() : pe,
      He = (So(Pe) ? Pe.current : Pe) || null || null;
    He !== fe.current && (be.setPositionReference(He), (fe.current = He));
  }, [x, be, I, L]),
    m.useEffect(() => {
      if (!x) return;
      const pe = L.current;
      typeof pe != "function" &&
        So(pe) &&
        pe.current !== fe.current &&
        (be.setPositionReference(pe.current), (fe.current = pe.current));
    }, [x, be, I, L]),
    m.useEffect(() => {
      if (g && x && ee.domReference && ee.floating)
        return uo(ee.domReference, ee.floating, Re, q);
    }, [g, x, ee, Re, q]));
  const we = tt(Ve),
    $e = ca(r, we, H),
    Ue = _t(Ve) || "center",
    We = !!_e.hide?.referenceHidden;
  xe(() => {
    w && x && K && T(we);
  }, [w, x, K, we]);
  const Ke = m.useMemo(
      () => ({ position: "absolute", top: _e.arrow?.y, left: _e.arrow?.x }),
      [_e.arrow],
    ),
    Ye = _e.arrow?.centerOffset !== 0;
  return m.useMemo(
    () => ({
      positionerStyles: le,
      arrowStyles: Ke,
      arrowRef: ue,
      arrowUncentered: Ye,
      side: $e,
      align: Ue,
      physicalSide: we,
      anchorHidden: We,
      refs: be,
      context: F,
      isPositioned: K,
      update: Re,
    }),
    [le, Ke, ue, Ye, $e, Ue, we, We, be, F, K, Re],
  );
}
function So(e) {
  return e != null && "current" in e;
}
function ua(e) {
  return e === "starting" ? su : Xe;
}
function uf(
  e,
  t,
  {
    styles: n,
    transitionStatus: r,
    props: s,
    refs: o,
    hidden: i,
    inert: a = !1,
  },
) {
  const f = { ...n };
  return (
    a && (f.pointerEvents = "none"),
    Nt("div", e, {
      state: t,
      ref: o,
      props: [{ role: "presentation", hidden: i, style: f }, ua(r), s],
      stateAttributesMapping: Sn,
    })
  );
}
const df = m.forwardRef(function (t, n) {
    const {
        render: r,
        className: s,
        anchor: o,
        positionMethod: i = "absolute",
        side: a = "top",
        align: f = "center",
        sideOffset: u = 0,
        alignOffset: l = 0,
        collisionBoundary: d = "clipping-ancestors",
        collisionPadding: p = 5,
        arrowPadding: g = 5,
        sticky: h = !1,
        disableAnchorTracking: x = !1,
        collisionAvoidance: v = iu,
        style: S,
        ...b
      } = t,
      C = vn(),
      w = Jd(),
      R = C.useState("open"),
      E = C.useState("mounted"),
      T = C.useState("trackCursorAxis"),
      O = C.useState("disableHoverablePopup"),
      A = C.useState("floatingRootContext"),
      j = C.useState("instantType"),
      $ = C.useState("transitionStatus"),
      P = C.useState("hasViewport"),
      I = cf({
        anchor: o,
        positionMethod: i,
        floatingRootContext: A,
        mounted: E,
        side: a,
        sideOffset: u,
        align: f,
        alignOffset: l,
        collisionBoundary: d,
        collisionPadding: p,
        sticky: h,
        arrowPadding: g,
        disableAnchorTracking: x,
        keepMounted: w,
        collisionAvoidance: v,
        adaptiveOrigin: P ? lf : void 0,
      }),
      L = m.useMemo(
        () => ({
          open: R,
          side: I.side,
          align: I.align,
          anchorHidden: I.anchorHidden,
          instant: T !== "none" ? "tracking-cursor" : j,
        }),
        [R, I.side, I.align, I.anchorHidden, T, j],
      ),
      k = uf(t, L, {
        styles: I.positionerStyles,
        transitionStatus: $,
        props: b,
        refs: [n, C.useStateSetter("positionerElement")],
        hidden: !E,
        inert: !R || T === "both" || O,
      });
    return c.jsx(aa.Provider, { value: I, children: k });
  }),
  ff = { ...Sn, ...vs },
  pf = m.forwardRef(function (t, n) {
    const { render: r, className: s, style: o, ...i } = t,
      a = vn(),
      { side: f, align: u } = la(),
      l = a.useState("open"),
      d = a.useState("instantType"),
      p = a.useState("transitionStatus"),
      g = a.useState("popupProps"),
      h = a.useState("floatingRootContext"),
      x = a.useState("disabled"),
      v = a.useState("closeDelay");
    (ys({
      open: l,
      ref: a.context.popupRef,
      onComplete() {
        l && a.context.onOpenChangeComplete?.(!0);
      },
    }),
      Pd(h, { enabled: !x, closeDelay: v }));
    const S = a.useStateSetter("popupElement");
    return Nt("div", t, {
      state: { open: l, side: f, align: u, instant: d, transitionStatus: p },
      ref: [n, a.context.popupRef, S],
      props: [g, ua(p), i],
      stateAttributesMapping: ff,
    });
  }),
  hf = m.forwardRef(function (t, n) {
    const { render: r, className: s, style: o, ...i } = t,
      a = vn(),
      {
        arrowRef: f,
        side: u,
        align: l,
        arrowUncentered: d,
        arrowStyles: p,
      } = la(),
      g = a.useState("open"),
      h = a.useState("instantType");
    return Nt("div", t, {
      state: { open: g, side: u, align: l, uncentered: d, instant: h },
      ref: [n, f],
      props: [{ style: p, "aria-hidden": !0 }, i],
      stateAttributesMapping: Sn,
    });
  }),
  mf = function (t) {
    const { delay: n, closeDelay: r, timeout: s = 400 } = t,
      o = m.useMemo(() => ({ delay: n, closeDelay: r }), [n, r]),
      i = m.useMemo(() => ({ open: n, close: r }), [n, r]);
    return c.jsx(sa.Provider, {
      value: o,
      children: c.jsx(hc, { delay: i, timeoutMs: s, children: t.children }),
    });
  };
function gf(e) {
  return fs(19) ? e : e ? "true" : void 0;
}
function xf(...e) {
  return e.filter(Boolean).join(" ");
}
function Zr({ delay: e = 0, ...t }) {
  return c.jsx(mf, { "data-slot": "tooltip-provider", delay: e, ...t });
}
function Qr({ ...e }) {
  return c.jsx($d, { "data-slot": "tooltip", ...e });
}
function Jr({ ...e }) {
  return c.jsx(Qd, { "data-slot": "tooltip-trigger", ...e });
}
function es({
  className: e,
  side: t = "top",
  sideOffset: n = 4,
  align: r = "center",
  alignOffset: s = 0,
  children: o,
  ...i
}) {
  return c.jsx(tf, {
    children: c.jsx(df, {
      align: r,
      alignOffset: s,
      side: t,
      sideOffset: n,
      className: "isolate z-50",
      children: c.jsxs(pf, {
        "data-slot": "tooltip-content",
        className: xf(
          "data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 rounded-none px-3 py-1.5 text-xs data-[side=inline-start]:slide-in-from-right-2 data-[side=inline-end]:slide-in-from-left-2 bg-foreground text-background z-50 w-fit max-w-xs origin-(--transform-origin)",
          typeof e == "string" ? e : void 0,
        ),
        ...i,
        children: [
          o,
          c.jsx(hf, {
            className:
              "size-2.5 translate-y-[calc(-50%-2px)] rotate-45 rounded-none data-[side=inline-end]:top-1/2! data-[side=inline-end]:-left-1 data-[side=inline-end]:-translate-y-1/2 data-[side=inline-start]:top-1/2! data-[side=inline-start]:-right-1 data-[side=inline-start]:-translate-y-1/2 bg-foreground fill-foreground z-50 data-[side=bottom]:top-1 data-[side=left]:top-1/2! data-[side=left]:-right-1 data-[side=left]:-translate-y-1/2 data-[side=right]:top-1/2! data-[side=right]:-left-1 data-[side=right]:-translate-y-1/2 data-[side=top]:-bottom-2.5",
          }),
        ],
      }),
    }),
  });
}
const xt = "#ffbf40",
  bt = "#6eaaff",
  bf = [
    y.BuilderBot,
    y.Barrier,
    y.Conveyor,
    y.Splitter,
    y.Harvester,
    y.Gunner,
    y.Sentinel,
    y.Launcher,
  ],
  vf = {
    [y.BuilderBot]: "#f59e0b",
    [y.Barrier]: "#f97316",
    [y.Conveyor]: "#60a5fa",
    [y.Splitter]: "#34d399",
    [y.Harvester]: "#22c55e",
    [y.Gunner]: "#ef4444",
    [y.Sentinel]: "#06b6d4",
    [y.Launcher]: "#eab308",
  };
function yf(e) {
  return [...e.toUpperCase()]
    .map((t) => String.fromCodePoint(t.charCodeAt(0) - 65 + 127462))
    .join("");
}
const Sf = new Intl.DisplayNames(["en"], { type: "region" });
function wf(e) {
  try {
    return Sf.of(e.toUpperCase()) ?? e;
  } catch {
    return e;
  }
}
function Cf({ name: e, supporter: t, country: n, right: r }) {
  const s = t
    ? {
        background: "linear-gradient(90deg, #f4c4f3, #fc67fa)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
        backgroundClip: "text",
      }
    : { color: "var(--vis-text-2)" };
  return c.jsxs("span", {
    className: `cursor-default flex min-w-0 max-w-[55%] items-center gap-0.5 overflow-hidden ${r ? "flex-row-reverse ml-auto" : ""}`,
    children: [
      c.jsx("span", {
        className: `flex-1 truncate text-xs font-medium ${r ? "text-right" : ""}`,
        style: s,
        children: e,
      }),
      n
        ? c.jsx(Zr, {
            children: c.jsxs(Qr, {
              children: [
                c.jsx(Jr, {
                  render: c.jsx("span", {
                    className:
                      "shrink-0 px-1 text-[14px] leading-none cursor-default",
                  }),
                  children: yf(n),
                }),
                c.jsx(es, { children: wf(n) }),
              ],
            }),
          })
        : null,
    ],
  });
}
function Tf(e) {
  return e === "international" ? "INT'L" : e === "uk" ? "UK" : "";
}
function Ef(e) {
  return e === "novice" ? "NOVICE" : e === "main" ? "MAIN" : "NON-STUDENT";
}
function wo(e, t) {
  const n = Tf(e),
    r = Ef(t);
  return n && r ? `${n} / ${r}` : n || r;
}
function Rf({ score: e, maxScore: t, side: n }) {
  const r = Array.from({ length: t }, (o, i) => i < e),
    s = n === "right" ? [...r].toReversed() : r;
  return c.jsx("div", {
    className: "flex items-center gap-2",
    children: s.map((o, i) =>
      c.jsx(
        "div",
        {
          className: "h-2.5 w-2.5 rotate-45 border-2",
          style: {
            borderColor: "var(--vis-text-3)",
            backgroundColor: o ? "var(--vis-text-3)" : "transparent",
          },
        },
        i,
      ),
    ),
  });
}
function Co({
  name: e,
  division: t,
  score: n,
  maxScore: r,
  side: s,
  color: o,
}) {
  return c.jsxs("div", {
    className: "flex flex-shrink-0 flex-col gap-1",
    style: { alignItems: s === "left" ? "flex-start" : "flex-end" },
    children: [
      c.jsx("span", {
        className: "text-lg font-bold leading-tight",
        style: { color: o },
        children: e,
      }),
      t &&
        c.jsx("span", {
          className:
            "text-[14px] font-semibold uppercase tracking-widest text-[var(--vis-text-3)]",
          children: t,
        }),
      c.jsx("div", {
        className: "flex pt-3",
        children: c.jsx(Rf, { score: n, maxScore: r, side: s }),
      }),
    ],
  });
}
const kf = {
  [y.BuilderBot]: "Bots",
  [y.Conveyor]: "Conveyors",
  [y.Splitter]: "Splitters",
  [y.Harvester]: "Harvesters",
  [y.Barrier]: "Barriers",
  [y.Gunner]: "Gunners",
  [y.Sentinel]: "Sentinels",
  [y.Launcher]: "Launchers",
};
function To(e, t) {
  const n = new Map();
  for (const o of e.entities.values()) {
    if (o.team !== t) continue;
    const i = Ko[o.kind] ?? 0;
    i > 0 && n.set(o.kind, (n.get(o.kind) ?? 0) + i);
  }
  const r = bf.map((o) => ({
      id: o,
      label: kf[o] ?? o,
      colour: vf[o] ?? "#94a3b8",
      value: n.get(o) ?? 0,
    })),
    s = r.reduce((o, i) => o + i.value, 0);
  return { slices: r, totalBonus: s, totalScale: Math.round(100 + s) };
}
function Eo({ direction: e, position: t }) {
  return e === "none"
    ? c.jsx("span", { className: "w-3" })
    : c.jsx("span", {
        className: "inline-block w-3 text-center text-sm leading-none",
        "aria-hidden": e !== t,
        style: {
          color: e === "left" ? xt : bt,
          visibility: e === t ? "visible" : "hidden",
        },
        children: e === "left" ? "◀" : "▶",
      });
}
function Ro({ label: e, valueA: t, valueB: n, flashOnDecrease: r = !1 }) {
  const s = t > n ? "left" : n > t ? "right" : "none",
    o = m.useRef(t),
    i = m.useRef(n),
    [a, f] = m.useState(!1),
    [u, l] = m.useState(!1);
  m.useEffect(() => {
    r &&
      (t < o.current && (f(!0), setTimeout(() => f(!1), 400)),
      n < i.current && (l(!0), setTimeout(() => l(!1), 400)),
      (o.current = t),
      (i.current = n));
  }, [t, n, r]);
  const d = a ? "#ef4444" : xt,
    p = u ? "#ef4444" : bt;
  return c.jsxs("div", {
    className: "flex flex-1 items-center justify-center gap-4 px-2",
    children: [
      c.jsx("span", {
        className:
          "min-w-[4rem] text-right text-sm font-bold tabular-nums transition-colors duration-200",
        style: { color: d },
        children: t.toLocaleString(),
      }),
      c.jsx(Eo, { direction: s, position: "left" }),
      c.jsx("div", {
        className: "flex flex-col items-center w-16",
        children: c.jsx("span", {
          className:
            "text-[14px] font-semibold uppercase tracking-widest text-[var(--vis-text-3)]",
          children: e,
        }),
      }),
      c.jsx(Eo, { direction: s, position: "right" }),
      c.jsx("span", {
        className:
          "min-w-[4rem] text-left text-sm font-bold tabular-nums transition-colors duration-200",
        style: { color: p },
        children: n.toLocaleString(),
      }),
    ],
  });
}
const Af = 4;
function ko({
  label: e,
  colour: t,
  seed: n,
  peakRank: r,
  currentRank: s,
  ratingAtMatch: o,
  peakRating: i,
  members: a,
  gameData: f,
  side: u,
  sprintWins: l,
}) {
  const d = u === "right",
    p = m.useRef(f?.health ?? null),
    [g, h] = m.useState(!1);
  return (
    m.useEffect(() => {
      const x = f?.health ?? null;
      if (x !== null && p.current !== null && x < p.current) {
        h(!0);
        const v = setTimeout(() => h(!1), 400);
        return ((p.current = x), () => clearTimeout(v));
      }
      p.current = x;
    }, [f?.health]),
    c.jsxs("div", {
      className: "flex flex-1 flex-col gap-2",
      children: [
        c.jsxs("div", {
          className: "flex items-center justify-between gap-2",
          style: { flexDirection: d ? "row-reverse" : "row" },
          children: [
            c.jsxs("div", {
              className: "flex min-w-0 items-center gap-1",
              children: [
                c.jsx("span", {
                  className: "truncate text-base font-bold",
                  style: { color: t },
                  children: e,
                }),
                l?.map((x) =>
                  c.jsx(
                    "img",
                    {
                      src: `/images/sprint-badges/sprint${x}.png`,
                      alt: `Sprint ${x} winner`,
                      title: `Sprint ${x} winner`,
                      style: { width: 16, height: 16, flexShrink: 0 },
                    },
                    x,
                  ),
                ),
              ],
            }),
            c.jsx("span", {
              className:
                "flex-shrink-0 text-sm font-semibold text-[var(--vis-text-3)]",
              children: n != null ? `#${n}` : "—",
            }),
          ],
        }),
        c.jsxs("div", {
          className: `flex flex-col gap-1.5 ${d ? "items-end" : ""}`,
          children: [
            c.jsxs("div", {
              className: `flex flex-col gap-0.5 ${d ? "items-end" : ""}`,
              children: [
                c.jsxs("div", {
                  className: "flex items-baseline gap-1.5",
                  children: [
                    c.jsx("span", {
                      className:
                        "text-base font-bold tabular-nums leading-none text-[var(--vis-text-1)]",
                      children: s != null ? `#${s}` : "—",
                    }),
                    c.jsxs("span", {
                      className:
                        "text-sm font-semibold tabular-nums leading-none",
                      style: { color: r != null ? t : "var(--vis-text-4)" },
                      children: ["(", r != null ? `#${r}` : "—", ")"],
                    }),
                  ],
                }),
                c.jsxs("span", {
                  className:
                    "text-[14px] uppercase tracking-wider text-[var(--vis-text-3)]",
                  children: [
                    "Rank",
                    c.jsx("span", {
                      className: "pl-1 text-[var(--vis-text-4)]",
                      children: "(peak)",
                    }),
                  ],
                }),
              ],
            }),
            c.jsxs("div", {
              className: `flex flex-col gap-0.5 ${d ? "items-end" : ""}`,
              children: [
                c.jsxs("div", {
                  className: "flex items-baseline gap-1.5",
                  children: [
                    c.jsx("span", {
                      className:
                        "text-base font-bold tabular-nums leading-none text-[var(--vis-text-1)]",
                      children: o != null ? Math.round(o) : "—",
                    }),
                    c.jsxs("span", {
                      className:
                        "text-sm font-semibold tabular-nums leading-none",
                      style: { color: i != null ? t : "var(--vis-text-4)" },
                      children: ["(", i != null ? Math.round(i) : "—", ")"],
                    }),
                  ],
                }),
                c.jsxs("span", {
                  className:
                    "text-[14px] uppercase tracking-wider text-[var(--vis-text-3)]",
                  children: [
                    "Rating",
                    c.jsx("span", {
                      className: "pl-1 text-[var(--vis-text-4)]",
                      children: "(peak)",
                    }),
                  ],
                }),
              ],
            }),
          ],
        }),
        c.jsx("div", {
          className: "flex flex-col gap-0.5",
          children: Array.from({ length: Af }, (x, v) => {
            const S = a?.[v];
            return S
              ? c.jsxs(
                  "div",
                  {
                    className: "flex items-center gap-1.5 overflow-hidden",
                    style: { flexDirection: d ? "row-reverse" : "row" },
                    children: [
                      S.image
                        ? c.jsx("img", {
                            src: S.image,
                            alt: "",
                            className:
                              "size-6 flex-shrink-0 rounded-full object-cover",
                          })
                        : c.jsx("div", {
                            className:
                              "size-6 flex-shrink-0 rounded-full bg-[var(--vis-bg-elevated)] flex items-center justify-center text-[10px] font-bold uppercase text-[var(--vis-text-2)]",
                            children: S.name.charAt(0),
                          }),
                      c.jsxs("div", {
                        className:
                          "flex min-w-0 flex-1 items-center gap-1 overflow-hidden",
                        children: [
                          d && S.affiliation
                            ? c.jsx(Zr, {
                                children: c.jsxs(Qr, {
                                  children: [
                                    c.jsx(Jr, {
                                      render: c.jsx("span", {
                                        className:
                                          "shrink truncate text-[10px] text-[var(--vis-text-3)] cursor-default",
                                      }),
                                      children: S.affiliation,
                                    }),
                                    c.jsx(es, { children: S.affiliation }),
                                  ],
                                }),
                              })
                            : null,
                          c.jsx(Cf, {
                            name: S.name,
                            supporter: S.supporter,
                            country: S.country,
                            right: d,
                          }),
                          !d && S.affiliation
                            ? c.jsx(Zr, {
                                children: c.jsxs(Qr, {
                                  children: [
                                    c.jsx(Jr, {
                                      render: c.jsx("span", {
                                        className:
                                          "ml-auto shrink truncate text-[9px] text-[var(--vis-text-3)] cursor-default",
                                      }),
                                      children: S.affiliation,
                                    }),
                                    c.jsx(es, { children: S.affiliation }),
                                  ],
                                }),
                              })
                            : null,
                        ],
                      }),
                    ],
                  },
                  S.userId,
                )
              : c.jsx("div", { className: "h-4" }, v);
          }),
        }),
        f &&
          c.jsxs(c.Fragment, {
            children: [
              c.jsx("div", { className: "h-px bg-[var(--vis-border)]" }),
              c.jsx("span", {
                className: `uppercase text-sm font-semibold text-[var(--vis-text-3)] ${d ? "text-right" : ""}`,
                children: "Wincon",
              }),
              c.jsxs("div", {
                className:
                  "flex flex-col gap-y-0.5 text-sm text-[var(--vis-text-2)]",
                children: [
                  c.jsxs("div", {
                    className:
                      "flex w-full items-center justify-between gap-x-2 transition-colors duration-200",
                    style: { color: g ? "#ef4444" : void 0 },
                    children: [
                      c.jsx("span", {
                        className: "font-bold",
                        children: "Health",
                      }),
                      c.jsx("span", {
                        className: "text-right tabular-nums",
                        children: f.health,
                      }),
                    ],
                  }),
                  c.jsxs("div", {
                    className: `flex w-full items-center justify-between gap-x-2 ${f.wincon?.wincon === "titaniumDelivered" ? (f.wincon?.winning ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : ""}`,
                    children: [
                      c.jsx("span", {
                        className: "font-bold",
                        children: "Titanium delivered",
                      }),
                      c.jsx("span", {
                        className: "text-right tabular-nums",
                        children: f.resources.titaniumCollected,
                      }),
                    ],
                  }),
                  c.jsxs("div", {
                    className: `flex w-full items-center justify-between gap-x-2 ${f.wincon?.wincon === "harvestersAlive" ? (f.wincon?.winning ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : ""}`,
                    children: [
                      c.jsx("span", {
                        className: "font-bold",
                        children: "Harvesters alive",
                      }),
                      c.jsx("span", {
                        className: "text-right tabular-nums",
                        children: f.harvestersAlive,
                      }),
                    ],
                  }),
                  c.jsxs("div", {
                    className: `flex w-full items-center justify-between gap-x-2 ${f.wincon?.wincon === "titaniumStored" ? (f.wincon?.winning ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : ""}`,
                    children: [
                      c.jsx("span", {
                        className: "font-bold",
                        children: "Titanium stored",
                      }),
                      c.jsx("span", {
                        className: "text-right tabular-nums",
                        children: f.resources.titanium,
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
      ],
    })
  );
}
function Of({
  games: e,
  match: t,
  selectedGameNumber: n,
  loadingGame: r,
  onSelectGame: s,
  revealedGames: o,
}) {
  return c.jsxs("div", {
    className: "flex flex-col gap-1",
    children: [
      c.jsx("span", {
        className:
          "pb-0.5 text-[14px] font-semibold uppercase tracking-widest text-[var(--vis-text-3)]",
        children: "Games",
      }),
      e.map((i) => {
        const a = i.gameNumber === n,
          f = o?.has(i.gameNumber) ?? !1,
          u =
            (i.winnerId != null && i.winnerId === t.teamAId) ||
            i.winnerSide === "a",
          l =
            (i.winnerId != null && i.winnerId === t.teamBId) ||
            i.winnerSide === "b",
          d = u ? xt : l ? bt : void 0,
          p = u ? t.teamAName : l ? t.teamBName : null;
        return c.jsxs(
          "button",
          {
            onClick: () => s?.(i.gameNumber),
            disabled: !i.replayS3Key || r,
            className: `flex items-center gap-1.5 rounded-lg px-2 py-1 text-left  transition-all ${a ? "border border-[#ffbf40]/40 bg-[#ffbf40]/15 text-[var(--vis-text-1)]" : "border border-transparent text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated)] hover:text-[var(--vis-text-1)]"} disabled:cursor-not-allowed disabled:opacity-30`,
            children: [
              c.jsx("span", {
                className:
                  "w-4 font-mono tabular-nums text-[var(--vis-text-3)]",
                children: i.gameNumber,
              }),
              c.jsx("span", {
                className: "flex-1 truncate",
                children: i.mapName,
              }),
              f && p && d
                ? c.jsx("span", {
                    className: "max-w-[3rem] truncate",
                    style: { color: d },
                    children: p,
                  })
                : c.jsx("span", {
                    className: "text-[var(--vis-text-4)]",
                    children: "???",
                  }),
              f &&
                i.turnsPlayed != null &&
                c.jsxs("span", {
                  className: "tabular-nums text-[var(--vis-text-4)]",
                  children: [i.turnsPlayed, "t"],
                }),
            ],
          },
          i.gameNumber,
        );
      }),
    ],
  });
}
function jf({
  phaserRef: e,
  assetBaseUrl: t,
  replay: n,
  turn: r,
  maxTurn: s,
  playing: o,
  speed: i,
  botStepMode: a,
  subStep: f,
  maxSubSteps: u,
  onPrev: l,
  onNext: d,
  onPlayPause: p,
  onSpeedUp: g,
  onSlowDown: h,
  onSliderChange: x,
  gameState: v,
  matchData: S,
  swapTeams: b = !1,
  selectedGameNumber: C,
  loadingGame: w,
  onSelectGame: R,
  revealedGames: E,
  tournamentName: T,
  roundName: O,
  hoveredTile: A,
  selectedTile: j,
  showAllIndicators: $ = !1,
  onToggleShowAllIndicators: P,
  theme: H = "dark",
}) {
  const N = S?.match,
    D = Math.ceil((S?.games.length ?? 1) / 2),
    { revealedScoreA: U, revealedScoreB: Q } = m.useMemo(() => {
      if (!S?.games || !N) return { revealedScoreA: 0, revealedScoreB: 0 };
      let le = 0,
        fe = 0;
      for (const we of S.games) {
        if (!E?.has(we.gameNumber)) continue;
        const $e =
            (we.winnerId != null && we.winnerId === N.teamAId) ||
            we.winnerSide === "a",
          Ue =
            (we.winnerId != null && we.winnerId === N.teamBId) ||
            we.winnerSide === "b";
        ($e && le++, Ue && fe++);
      }
      return { revealedScoreA: le, revealedScoreB: fe };
    }, [S, N, E]),
    ve = N?.teamAName ?? "Gold",
    Y = N?.teamBName ?? "Silver",
    J = N?.teamARegion,
    ce = N?.teamACategory,
    z = N?.teamBRegion,
    ue = N?.teamBCategory,
    X = N?.teamAMembers,
    te = N?.teamBMembers,
    ye = N?.teamAPeakRank,
    W = N?.teamBPeakRank,
    B = N?.teamACurrentRank ?? null,
    G = N?.teamBCurrentRank ?? null,
    ne = N?.teamARatingAtMatch ?? null,
    de = N?.teamBRatingAtMatch ?? null,
    se = N?.teamAPeakRating ?? null,
    q = N?.teamBPeakRating ?? null,
    be = N?.teamASeed ?? null,
    ee = N?.teamBSeed ?? null,
    Ne = N?.teamASprintWins,
    Me = N?.teamBSprintWins,
    _e = S?.games.find((le) => le.gameNumber === C)?.mapName ?? null,
    Re = m.useMemo(() => {
      if (!v) return null;
      const le = b ? re.B : re.A,
        fe = b ? re.A : re.B;
      let we = 0,
        $e = 0,
        Ue = 500,
        We = 500,
        Ke = null,
        Ye = null;
      for (const Se of v.entities.values())
        Se.kind === y.Core &&
          (Se.team === le
            ? ((we = Se.hp), (Ue = Se.maxHp), (Ke = Se.position))
            : Se.team === fe &&
              (($e = Se.hp), (We = Se.maxHp), (Ye = Se.position)));
      const [pe, Pe] = b
        ? [v.players[1], v.players[0]]
        : [v.players[0], v.players[1]];
      return {
        hpA: we,
        hpB: $e,
        maxHpA: Ue,
        maxHpB: We,
        corePosA: Ke,
        corePosB: Ye,
        titaniumA: pe.titaniumCollected,
        titaniumB: Pe.titaniumCollected,
      };
    }, [v, b]),
    Ve = m.useMemo(() => {
      if (!v) return null;
      const le = b ? re.B : re.A,
        fe = b ? re.A : re.B,
        [we, $e] = b
          ? [v.players[1], v.players[0]]
          : [v.players[0], v.players[1]];
      let Ue = 0,
        We = 0,
        Ke = 0,
        Ye = 0;
      for (const De of v.entities.values())
        De.kind === y.Harvester
          ? De.team === le
            ? Ue++
            : De.team === fe && We++
          : De.kind === y.Core &&
            (De.team === le ? (Ke = De.hp) : De.team === fe && (Ye = De.hp));
      const pe = Ke !== Ye ? Ke > Ye : null,
        Pe = Ke !== Ye ? Ye > Ke : null;
      let Se = null,
        He = null;
      return (
        we.titaniumCollected !== $e.titaniumCollected
          ? ((Se = {
              wincon: "titaniumDelivered",
              winning: we.titaniumCollected > $e.titaniumCollected,
            }),
            (He = {
              wincon: "titaniumDelivered",
              winning: $e.titaniumCollected > we.titaniumCollected,
            }))
          : Ue !== We
            ? ((Se = { wincon: "harvestersAlive", winning: Ue > We }),
              (He = { wincon: "harvestersAlive", winning: We > Ue }))
            : we.titanium !== $e.titanium &&
              ((Se = {
                wincon: "titaniumStored",
                winning: we.titanium > $e.titanium,
              }),
              (He = {
                wincon: "titaniumStored",
                winning: $e.titanium > we.titanium,
              })),
        {
          left: {
            colour: xt,
            health: Ke,
            healthLeading: pe,
            resources: we,
            harvestersAlive: Ue,
            scaleData: To(v, le),
            wincon: Se ?? void 0,
          },
          right: {
            colour: bt,
            health: Ye,
            healthLeading: Pe,
            resources: $e,
            harvestersAlive: We,
            scaleData: To(v, fe),
            wincon: He ?? void 0,
          },
        }
      );
    }, [v, b]),
    [F, K] = m.useState(null),
    [oe, je] = m.useState(!1);
  m.useEffect(() => {
    K(null);
    if (!n) {
      return;
    }
    const le = requestAnimationFrame(() => {
      K(n.computeTimeSeries(Ko));
    });
    return () => cancelAnimationFrame(le);
  }, [n]);
  const Fe = m.useMemo(() => {
      const le = b ? F?.titaniumB : F?.titaniumA,
        fe = b ? F?.titaniumA : F?.titaniumB;
      return !le || !fe
        ? []
        : [
            { label: "", colour: xt, data: le },
            { label: "", colour: bt, data: fe },
          ];
    }, [F, b]),
    ct = m.useMemo(() => {
      const le = b ? F?.titaniumCollectedB : F?.titaniumCollectedA,
        fe = b ? F?.titaniumCollectedA : F?.titaniumCollectedB;
      return !le || !fe
        ? []
        : [
            { label: "", colour: xt, data: le },
            { label: "", colour: bt, data: fe },
          ];
    }, [F, b]);
  return (
    m.useMemo(() => {
      const le = b ? F?.scaleB : F?.scaleA,
        fe = b ? F?.scaleA : F?.scaleB;
      return !le || !fe
        ? []
        : [
            { label: "", colour: xt, data: le },
            { label: "", colour: bt, data: fe },
          ];
    }, [F, b]),
    m.useMemo(() => {
      const le = b ? F?.harvestersB : F?.harvestersA,
        fe = b ? F?.harvestersA : F?.harvestersB;
      return !le || !fe
        ? []
        : [
            { label: "", colour: xt, data: le },
            { label: "", colour: bt, data: fe },
          ];
    }, [F, b]),
    c.jsxs("div", {
      className:
        "relative flex h-full w-full flex-col gap-1.5 overflow-hidden p-1",
      children: [
        c.jsxs("div", {
          className: "flex w-full flex-shrink-0 gap-1.5",
          children: [
            c.jsx("div", {
              className:
                "w-58 flex-shrink-0 h-24 rounded-xl flex items-center justify-center",
              children: c.jsx(Lo, {}),
            }),
            c.jsxs("div", {
              className:
                "flex h-24 min-w-0 flex-1 items-center justify-between rounded-xl px-2",
              children: [
                N &&
                  c.jsx(Co, {
                    name: ve,
                    division: wo(J, ce),
                    score: U,
                    maxScore: D,
                    side: "left",
                    color: xt,
                  }),
                c.jsx("div", {
                  className: "flex flex-col items-center gap-0.5",
                  children:
                    Re &&
                    c.jsxs(c.Fragment, {
                      children: [
                        c.jsx(Ro, {
                          label: "Health",
                          valueA: Re.hpA,
                          valueB: Re.hpB,
                          flashOnDecrease: !0,
                        }),
                        c.jsx(Ro, {
                          label: "Titanium",
                          valueA: Re.titaniumA,
                          valueB: Re.titaniumB,
                        }),
                      ],
                    }),
                }),
                N &&
                  c.jsx(Co, {
                    name: Y,
                    division: wo(z, ue),
                    score: Q,
                    maxScore: D,
                    side: "right",
                    color: bt,
                  }),
              ],
            }),
            c.jsxs("div", {
              className:
                "relative w-58 flex-shrink-0 h-24 rounded-xl p-2 flex flex-col items-center justify-center gap-1",
              children: [
                T &&
                  c.jsx("span", {
                    className:
                      "text-base font-bold uppercase tracking-widest text-[var(--vis-text-1)] text-center",
                    children: T,
                  }),
                O &&
                  c.jsx("span", {
                    className:
                      " font-semibold uppercase tracking-widest text-[var(--vis-text-3)] text-center",
                    children: O,
                  }),
                N && S?.games && S.games.length > 0
                  ? c.jsxs(c.Fragment, {
                      children: [
                        c.jsxs("button", {
                          onClick: () => je((le) => !le),
                          className:
                            "mt-0.5 flex items-center gap-1 rounded-md px-2 py-0.5  font-semibold text-[var(--vis-text-3)] hover:bg-[var(--vis-bg-elevated)] transition-colors",
                          children: [
                            C != null
                              ? `Game ${C}${_e ? ` / ${_e}` : ""}`
                              : "Select game",
                            c.jsx("span", {
                              className: "text-[10px] opacity-60",
                              children: oe ? "▲" : "▼",
                            }),
                          ],
                        }),
                        oe &&
                          c.jsxs(c.Fragment, {
                            children: [
                              c.jsx("button", {
                                className: "fixed inset-0 z-10 cursor-default",
                                tabIndex: -1,
                                onClick: () => je(!1),
                                onKeyDown: (le) =>
                                  le.key === "Escape" && je(!1),
                                "aria-label": "Close game selector",
                              }),
                              c.jsx("div", {
                                className:
                                  "absolute right-0 top-full z-20 mt-1 w-64 rounded-lg border border-[var(--vis-border)] bg-[var(--vis-bg-panel)] shadow-lg p-1",
                                children: c.jsx(Of, {
                                  games: S.games,
                                  match: N,
                                  selectedGameNumber: C,
                                  loadingGame: w,
                                  onSelectGame: (le) => {
                                    (R?.(le), je(!1));
                                  },
                                  revealedGames: E,
                                }),
                              }),
                            ],
                          }),
                      ],
                    })
                  : C != null
                    ? c.jsxs("span", {
                        className:
                          " font-semibold uppercase tracking-widest text-[var(--vis-text-3)] text-center",
                        children: ["Game ", C, _e ? ` / ${_e}` : ""],
                      })
                    : null,
              ],
            }),
          ],
        }),
        c.jsxs("div", {
          className: "flex w-full min-h-0 flex-1 gap-1.5",
          children: [
            c.jsxs("div", {
              className: "flex w-58 flex-shrink-0 flex-col gap-1.5",
              children: [
                c.jsx("div", {
                  className:
                    "flex flex-shrink-0 flex-col rounded-xl border border-[var(--vis-border)] p-2",
                  children:
                    N &&
                    c.jsx(ko, {
                      label: ve,
                      colour: xt,
                      seed: be,
                      peakRank: ye ?? null,
                      currentRank: B ?? null,
                      ratingAtMatch: ne ?? null,
                      peakRating: se ?? null,
                      members: X,
                      gameData: Ve?.left ?? null,
                      side: "left",
                      sprintWins: Ne,
                    }),
                }),
                c.jsx("div", {
                  className: "flex flex-col flex-1 min-h-0 gap-1.5",
                  children: c.jsx(en, {
                    title: "Titanium",
                    series: Fe,
                    currentTurn: r,
                    maxTurn: s,
                    yFloor: 0,
                  }),
                }),
              ],
            }),
            c.jsxs("div", {
              className: "flex min-w-0 flex-1 flex-col gap-1.5",
              children: [
                c.jsxs("div", {
                  className:
                    "relative min-w-0 flex-1 overflow-hidden rounded-xl border border-[var(--vis-border)]",
                  children: [
                    n &&
                      c.jsxs("div", {
                        className:
                          "pointer-events-none absolute right-2 bottom-2 z-10 rounded-md border border-[var(--vis-border)] bg-[var(--vis-bg-panel-80)] px-2 py-1 font-semibold text-[#ffbf40] backdrop-blur-sm",
                        children: [i, "x"],
                      }),
                    c.jsx(Uo, { ref: e, assetBaseUrl: t, theme: H }),
                    j &&
                      c.jsx(Yo, {
                        selectedTile: j,
                        hoveredTile: A,
                        swapTeams: b,
                      }),
                  ],
                }),
                c.jsxs("div", {
                  className:
                    "flex-shrink-0 flex items-center gap-2 rounded-xl border border-[var(--vis-border)] px-2 py-1",
                  children: [
                    c.jsxs("div", {
                      className: "grid grid-cols-3 gap-1 w-28 flex-shrink-0",
                      children: [
                        c.jsx("button", {
                          className:
                            "grid h-7 place-items-center rounded-md bg-[var(--vis-bg-elevated)]  text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] disabled:opacity-30",
                          title: a ? "Previous bot step" : "Previous turn",
                          onClick: l,
                          disabled: !n || (r <= 0 && (!a || f <= 0)) || o,
                          children: "◀",
                        }),
                        c.jsx("button", {
                          className:
                            "grid h-7 place-items-center rounded-md bg-[#ffbf40]  font-bold text-black hover:bg-[#ffa800] disabled:opacity-30",
                          title: o ? "Pause" : "Play",
                          onClick: p,
                          disabled: !n,
                          children: o ? "❚❚" : "▶",
                        }),
                        c.jsx("button", {
                          className:
                            "grid h-7 place-items-center rounded-md bg-[var(--vis-bg-elevated)]  text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] disabled:opacity-30",
                          title: a ? "Next bot step" : "Next turn",
                          onClick: d,
                          disabled: !n || (r >= s && (!a || f >= u)) || o,
                          children: "▶",
                        }),
                      ],
                    }),
                    c.jsxs("div", {
                      className: "flex flex-1 flex-col gap-0.5 min-w-0",
                      children: [
                        c.jsxs("div", {
                          className: "flex items-center gap-2",
                          children: [
                            c.jsxs("div", {
                              className:
                                "grid grid-cols-3 items-center gap-1 w-20 flex-shrink-0",
                              children: [
                                c.jsx("button", {
                                  className:
                                    "grid h-6 place-items-center rounded-md bg-[var(--vis-bg-elevated)] text-[12px] font-semibold text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] disabled:opacity-30",
                                  onClick: h,
                                  disabled: !n || i <= 1,
                                  children: "½x",
                                }),
                                c.jsxs("span", {
                                  className:
                                    "text-center text-[10px] font-semibold tabular-nums text-[var(--vis-text-2)]",
                                  children: [i, "x"],
                                }),
                                c.jsx("button", {
                                  className:
                                    "grid h-6 place-items-center rounded-md bg-[var(--vis-bg-elevated)] text-[12px] font-semibold text-[var(--vis-text-2)] hover:bg-[var(--vis-bg-elevated-hover)] disabled:opacity-30",
                                  onClick: g,
                                  disabled: !n || i >= 256,
                                  children: "2x",
                                }),
                              ],
                            }),
                            c.jsx("span", {
                              className:
                                "text-[14px] tabular-nums text-[var(--vis-text-3)]",
                              children: n ? `${r}` : "–",
                            }),
                          ],
                        }),
                        c.jsx("input", {
                          type: "range",
                          "aria-label": "Turn",
                          min: 0,
                          max: 2e3,
                          value: r,
                          onChange: x,
                          disabled: !n,
                          className:
                            "w-full disabled:opacity-30 [appearance:none] h-1.5 rounded-full cursor-pointer [&::-webkit-slider-thumb]:[appearance:none] [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[#ffbf40] [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-[#ffbf40] [&::-moz-range-thumb]:border-0",
                          style: {
                            background: `linear-gradient(to right, #ffbf40 0%, #ffbf40 ${(r / 2e3) * 100}%, var(--vis-bg-elevated) ${(r / 2e3) * 100}%, var(--vis-bg-elevated) 100%)`,
                          },
                        }),
                      ],
                    }),
                    c.jsx("div", {
                      className: "flex flex-wrap gap-2 flex-shrink-0",
                      children: c.jsx(Rt, {
                        label: "Ind.",
                        checked: $,
                        onChange: P ?? (() => {}),
                      }),
                    }),
                  ],
                }),
              ],
            }),
            c.jsxs("div", {
              className: "flex w-58 flex-shrink-0 flex-col gap-1.5",
              children: [
                c.jsx("div", {
                  className:
                    "flex flex-shrink-0 flex-col rounded-xl border border-[var(--vis-border)] p-2",
                  children:
                    N &&
                    c.jsx(ko, {
                      label: Y,
                      colour: bt,
                      seed: ee,
                      peakRank: W ?? null,
                      currentRank: G ?? null,
                      ratingAtMatch: de ?? null,
                      peakRating: q ?? null,
                      members: te,
                      gameData: Ve?.right ?? null,
                      side: "right",
                      sprintWins: Me,
                    }),
                }),
                c.jsx("div", {
                  className: "flex flex-col flex-1 min-h-0 gap-1.5",
                  children: c.jsx(en, {
                    title: "Ti Collected",
                    series: ct,
                    currentTurn: r,
                    maxTurn: s,
                    yFloor: 0,
                  }),
                }),
              ],
            }),
          ],
        }),
      ],
    })
  );
}
function extractOarenaProfilerRecords(replay) {
  const extract = globalThis.__OARENA_SQUARE_BRIDGE__?.extractProfilerReports;
  if (typeof extract !== "function") return [];
  const reports = [];
  for (const updates of replay?.rawTurnUpdates ?? []) {
    for (const update of updates ?? []) {
      const output = update?.botOutput;
      if (!output || typeof output.stdout !== "string" || !output.stdout) continue;
      const captured = extract(output.stdout);
      output.stdout = captured.text;
      reports.push(...captured.reports);
    }
  }
  return reports;
}

function kp({
  initialMatchId: e,
  initialGameNumber: t,
  initialReplayUrl: n,
  fetchMatch: r,
  fetchReplay: s,
  onGameSelect: o,
  assetBaseUrl: i,
  theme: initialTheme = "dark",
  tournamentMode: u = !1,
  tournamentName: d,
  roundName: p,
} = {}) {
  const h = m.useRef(null),
    [S, b] = m.useState(null),
    [C, w] = m.useState(!1),
    [R, E] = m.useState(null),
    [T, O] = m.useState(0),
    [A, j] = m.useState(0),
    [$, P] = m.useState(null),
    [I, L] = m.useState(!1),
    [k, M] = m.useState(1),
    [H, N] = m.useState(null),
    [D, U] = m.useState(null),
    [Q, ve] = m.useState(!1),
    [Y, J] = m.useState(0),
    [ce, z] = m.useState(0),
    [ue, X] = m.useState(!0),
    [de, se] = m.useState(!0),
    [q, be] = m.useState(!1),
    Ne = m.useRef(null),
    Ve = m.useRef(null),
    F = m.useRef(null),
    K = m.useRef(1),
    [oe, je] = m.useState(null),
    [Fe, ct] = m.useState(null),
    [le, fe] = m.useState(!1),
    [we, $e] = m.useState(!1),
    [Ue, We] = m.useState(null),
    [Ke, Ye] = m.useState(new Set()),
    [activeTheme, setActiveTheme] = m.useState(initialTheme),
    replayRef = m.useRef(null),
    loadGeneration = m.useRef(0),
    viewerVisible = m.useRef(!0),
    pe = oe?.games.find((_) => _.gameNumber === Fe)?.swapCores ?? !1,
    Pe = m.useCallback(() => {
      (Ve.current && (clearInterval(Ve.current), (Ve.current = null)),
        F.current !== null &&
          (cancelAnimationFrame(F.current), (F.current = null)));
    }, []),
    Se = m.useCallback(() => {
      (Pe(), L(!1));
    }, [Pe]),
    He = m.useCallback(
      (_, V = !1) => {
        const Ce = ++loadGeneration.current;
        if (!(_ instanceof ArrayBuffer))
          return Promise.reject(new Error("Replay bytes are required"));
        const Ee = fl(_, !0);
        Ee.profilerRecords = extractOarenaProfilerRecords(Ee);

        const ut = replayRef.current;
        if (ut && ut !== Ee) {
          ut.pauseBackgroundPrecompute();
          ut.dispose();
        }
        ((replayRef.current = Ee),
          Ee.startBackgroundPrecompute(),
          Pe(),
          L(!1),
          N(null),
          U(null),
          ve(!1),
          J(0),
          z(0),
          b(Ee),
          O(0),
          j(Ee.totalTurns),
          P(Ee.getState(0) ?? null));

        return new Promise((ut, rt) => {
          const As = h.current;
          if (!As) {
            rt(new Error("Square renderer is not ready"));
            return;
          }
          As.whenReady((fr) => {
            if (Ce !== loadGeneration.current) {
              ut({ superseded: !0 });
              return;
            }
            try {
              (fr.setSwapTeams(V),
                fr.setOnTurnChange((Ca, Ta) => {
                  (O(Ca), j(Ta));
                }),
                fr.setOnStateChange((Ca) => {
                  P(Ca);
                }),
                de && !u
                  ? fr.setOnHoverChange((Ca) => {
                      N(Ca);
                    })
                  : fr.setOnHoverChange(() => {}),
                fr.setOnSelectChange((Ca) => {
                  U(Ca);
                }),
                fr.setOnSubStepChange((Ca, Ta) => {
                  (J(Ca), z(Ta));
                }),
                fr.setOnBotStepModeChange((Ca) => {
                  ve(Ca);
                }),
                fr.loadReplay(Ee),
                ut({ superseded: !1 }));
            } catch (Ca) {
              rt(Ca);
            }
          });
        });
      },
      [de, u, Pe],
    );
  const handleBridgeTheme = m.useCallback((_) => {
      (_ === "light" || _ === "dark") && setActiveTheme(_);
    }, []),
    handleBridgeVisibility = m.useCallback(
      (_) => {
        viewerVisible.current = _;
        const V = h.current?.getGame(),
          ke = h.current?.getScene();
        if (_) {
          (replayRef.current?.startBackgroundPrecompute(),
            V?.loop?.wake?.(),
            ke?.scene?.wake?.());
        } else {
          (Se(),
            replayRef.current?.pauseBackgroundPrecompute(),
            ke?.scene?.sleep?.(),
            V?.loop?.sleep?.());
        }
      },
      [Se],
    ),
    handleBridgeLoad = m.useCallback(
      async ({ replay: _, game: V, theme: ke, key: Ce }) => {
        ke && handleBridgeTheme(ke);
        je({
          match: {
            teamAName:
              typeof V?.a === "string" && V.a.trim() ? V.a.trim() : "Team A",
            teamBName:
              typeof V?.b === "string" && V.b.trim() ? V.b.trim() : "Team B",
          },
          games: [],
        });
        ct(null);
        E(
          V?.map
            ? `Game ${V.id ?? Ce} — ${V.map}`
            : `Game ${V?.id ?? Ce ?? "replay"}`,
        );
        const Ee = await He(_, !1);
        if (!Ee?.superseded && !viewerVisible.current) {
          const ut = h.current?.getScene(),
            rt = h.current?.getGame();
          (replayRef.current?.pauseBackgroundPrecompute(),
            ut?.scene?.sleep?.(),
            rt?.loop?.sleep?.());
        }
        return {
          profilerRecords: Ee?.superseded
            ? []
            : replayRef.current?.profilerRecords ?? [],
        };
      },
      [He, handleBridgeTheme],
    );
  m.useEffect(() => {
    const _ = globalThis.__OARENA_SQUARE_BRIDGE__;
    if (!_?.connect || !h.current) return;
    let V = !1,
      ke = null;
    return (
      h.current.whenReady(() => {
        V ||
          (ke = _.connect(
            handleBridgeLoad,
            handleBridgeTheme,
            handleBridgeVisibility,
          ));
      }),
      () => {
        ((V = !0), ke?.());
      }
    );
  }, [
    handleBridgeLoad,
    handleBridgeTheme,
    handleBridgeVisibility,
  ]);
  m.useEffect(
    () => () => {
      (loadGeneration.current++, Pe());
      replayRef.current?.dispose();
      replayRef.current = null;
    },
    [Pe],
  );
  (m.useEffect(() => {
    const _ = window.matchMedia("(hover: hover) and (pointer: fine)"),
      V = () => se(_.matches);
    return (
      V(),
      _.addEventListener("change", V),
      () => _.removeEventListener("change", V)
    );
  }, []),
    m.useEffect(() => {
      const _ = Ne.current;
      if (!_ || typeof ResizeObserver > "u") return;
      const V = new ResizeObserver((ke) => {
        const Ce = ke[0]?.contentRect.width ?? 0;
        be(Ce >= 1024);
      });
      return (V.observe(_), () => V.disconnect());
    }, []));
  const De = m.useCallback(
      (_) => {
        if (!_.name.endsWith(".replay26")) {
          alert(`Invalid file: expected a .replay26 file, got "${_.name}".`);
          return;
        }
        (w(!0), E(_.name));
        const V = new FileReader();
        (V.addEventListener("load", async () => {
          try {
            await Promise.resolve(globalThis.__OARENA_FCODE_METADATA_READY__);
            await Promise.resolve(
              globalThis.__OARENA_LIVE_FCODE_METADATA_READY__,
            );
            globalThis.__OARENA_FCODE_METADATA__ =
              globalThis.__OARENA_LIVE_FCODE_METADATA__ ?? null;
            await He(V.result);
          } catch (_) {
            Rn.error("Failed to load replay file:", _);
          } finally {
            w(!1);
          }
        }),
          V.addEventListener("error", () => {
            (Rn.error("Failed to read file:", V.error), w(!1));
          }),
          V.readAsArrayBuffer(_));
      },
      [He],
    ),
    Je = m.useCallback(
      (_) => {
        const V = _.target.files?.[0];
        V && De(V);
      },
      [De],
    ),
    ht = m.useCallback(
      (_) => {
        De(_);
      },
      [De],
    );
  async function mt(_, V, ke) {
    if (r) {
      (fe(!0), We(null));
      try {
        const Ce = await r(_);
        if (ke?.aborted) return;
        (je(Ce), ct(null));
        const ut =
          (V
            ? Ce.games.find((rt) => rt.gameNumber === V && rt.replayS3Key)
            : null) ?? Ce.games.find((rt) => rt.replayS3Key);
        ut && s && (await $t(Ce, ut.gameNumber, ke));
      } catch (Ce) {
        if (ke?.aborted) return;
        (Rn.error("Failed to load match:", Ce),
          We(Ce instanceof Error ? Ce.message : "Failed to load match"));
      } finally {
        ke?.aborted || fe(!1);
      }
    }
  }
  async function $t(_, V, ke) {
    if (!s) return;
    const Ce = _.games.find((Ee) => Ee.gameNumber === V);
    if (Ce?.replayS3Key) {
      (O(0), j(0), b(null), P(null), ct(V), $e(!0), We(null));
      try {
        const Ee = await s(_.match.id, V);
        if (ke?.aborted) return;
        (await He(Ee, !!Ce.swapCores), E(`Game ${V} — ${Ce.mapName}`));
      } catch (Ee) {
        if (ke?.aborted) return;
        (Rn.error("Failed to load replay:", Ee),
          We(Ee instanceof Error ? Ee.message : "Failed to load replay"));
      } finally {
        ke?.aborted || $e(!1);
      }
    }
  }
  function Gt(_) {
    oe && (o?.(oe.match.id, _), $t(oe, _));
  }
  (m.useEffect(() => {
    !u ||
      Fe === null ||
      (T > 0 &&
        T >= A &&
        A > 0 &&
        Ye((_) => {
          if (_.has(Fe)) return _;
          const V = new Set(_);
          return (V.add(Fe), V);
        }));
  }, [u, T, A, Fe]),
    m.useEffect(() => {
      if (!e || !r) return;
      const _ = { aborted: !1 };
      return (
        mt(e, t, _),
        () => {
          _.aborted = !0;
        }
      );
    }, [e, t]),
    m.useEffect(() => {
      if (!n) return;
      let _ = !1;
      return (
        w(!0),
        Promise.resolve(globalThis.__OARENA_FCODE_METADATA_READY__)
          .then(() => fetch(n))
          .then(async (V) => {
            if (!V.ok) throw new Error(`HTTP ${V.status}`);
            return V.arrayBuffer();
          })
          .then(async (V) => {
            _ || (await He(V), E(n.split("/").pop() ?? "replay"), w(!1));
          })
          .catch((V) => {
            _ || (Rn.error("Failed to load replay from URL:", V), w(!1));
          }),
        () => {
          _ = !0;
        }
      );
    }, [n]));
  const Bt = m.useCallback(() => {
      h.current?.getScene()?.prevTurn();
    }, []),
    Mt = m.useCallback(() => {
      h.current?.getScene()?.nextTurn();
    }, []),
    wn = 1e3,
    ln = 16,
    Ct = m.useCallback(() => {
      Pe();
      const _ = K.current,
        V = h.current?.getScene();
      if (_ >= ln) {
        V && V.setAnimationDuration(0);
        let ke = performance.now(),
          Ce = 0;
        const Ee = (ut) => {
          const rt = h.current?.getScene();
          if (!rt) {
            F.current = requestAnimationFrame(Ee);
            return;
          }
          const As = ut - ke;
          ((ke = ut), (Ce += (K.current * As) / wn));
          const fr = Math.floor(Ce);
          if (((Ce -= fr), fr > 0)) {
            const Ca = rt.getTurn(),
              Ta = rt.getSubStep?.() ?? 0;
            if (
              rt.advanceTurns(fr) === 0 ||
              (rt.getTurn() === Ca && (rt.getSubStep?.() ?? 0) === Ta)
            ) {
              Se();
              return;
            }
          }
          F.current = requestAnimationFrame(Ee);
        };
        F.current = requestAnimationFrame(Ee);
      } else {
        const ke = wn / _;
        V && V.setAnimationDuration(ke);
        const Ce = () => {
          const Ee = h.current?.getScene();
          if (!Ee) return (Se(), !1);
          const ut = Ee.getTurn(),
            rt = Ee.getSubStep?.() ?? 0;
          return (
            Ee.nextTurn(!0),
            Ee.getTurn() !== ut || (Ee.getSubStep?.() ?? 0) !== rt
              ? !0
              : (Se(), !1)
          );
        };
        Ce() &&
          (Ve.current = setInterval(() => {
            Ce();
          }, ke));
      }
    }, [Se, Pe]),
    qt = m.useCallback(() => {
      I || Ve.current !== null || F.current !== null ? Se() : (L(!0), Ct());
    }, [Se, I, Ct]),
    Cn = () => Ve.current !== null || F.current !== null,
    gt = m.useCallback(() => {
      M((_) => {
        const V = Math.min(_ * 2, 256);
        return ((K.current = V), Cn() && Ct(), V);
      });
    }, [Ct]),
    Zt = m.useCallback(() => {
      M((_) => {
        const V = Math.max(_ / 2, 1);
        return ((K.current = V), Cn() && Ct(), V);
      });
    }, [Ct]),
    Tn = m.useCallback((_) => {
      const V = parseInt(_.target.value, 10);
      h.current?.getScene()?.setTurn(V);
    }, []),
    lr = m.useCallback(
      (_) => {
        I || h.current?.getScene()?.setTurn(_);
      },
      [I],
    );
  m.useEffect(() => {
    const _ = (V) => {
      const ke = V.target;
      ke.tagName === "TEXTAREA" ||
        (ke.tagName === "INPUT" && ke.type === "text") ||
        (V.key === "Escape"
          ? (h.current?.getScene()?.clearSelection(), U(null))
          : V.key === " "
            ? (V.preventDefault(), ke.blur(), qt())
            : V.key === "ArrowLeft"
              ? (V.preventDefault(), I ? Zt() : Bt())
              : V.key === "ArrowRight" &&
                (V.preventDefault(), I ? gt() : Mt()));
    };
    return (
      window.addEventListener("keydown", _),
      () => window.removeEventListener("keydown", _)
    );
  }, [qt, Bt, Mt, Zt, gt, I, U]);
  const ks = m.useCallback(() => {
      const _ = h.current?.getScene();
      _ && _.setBotStepMode(!_.getBotStepMode());
    }, []),
    cr = m.useCallback((_) => {
      (X(_), h.current?.getScene()?.setShowAllIndicators(_));
    }, []),
    xa =
      activeTheme === "dark"
        ? {
            "--vis-bg": "#000000",
            "--vis-bg-panel": "#111111",
            "--vis-bg-card": "#000000",
            "--vis-bg-elevated": "#1c1c1c",
            "--vis-bg-elevated-hover": "#262626",
            "--vis-bg-badge": "#0d0d0d",
            "--vis-bg-winner": "#0d0d00",
            "--vis-bg-code": "#000000",
            "--vis-bg-panel-80": "rgba(17,17,17,0.8)",
            "--vis-border": "rgba(255,255,255,0.1)",
            "--vis-border-2": "rgba(255,255,255,0.15)",
            "--vis-text-1": "#fafafa",
            "--vis-text-2": "#a1a1a1",
            "--vis-text-3": "#666666",
            "--vis-text-4": "#484848",
          }
        : {
            "--vis-bg": "#ffffff",
            "--vis-bg-panel": "#ffffff",
            "--vis-bg-card": "#ffffff",
            "--vis-bg-elevated": "#ebebeb",
            "--vis-bg-elevated-hover": "#e0e0e0",
            "--vis-bg-badge": "#f5f5f5",
            "--vis-bg-winner": "#fffde6",
            "--vis-bg-code": "#f0f0f0",
            "--vis-bg-panel-80": "rgba(248,248,248,0.8)",
            "--vis-border": "#d4d4d4",
            "--vis-border-2": "#c0c0c0",
            "--vis-text-1": "#1a1a1a",
            "--vis-text-2": "#444444",
            "--vis-text-3": "#777777",
            "--vis-text-4": "#aaaaaa",
          },
    ba = q
      ? "flex min-h-0 flex-1 flex-row gap-4 px-4 pb-4"
      : "flex min-h-0 flex-1 flex-col gap-2 px-2 pb-2 sm:px-3 sm:pb-3",
    va = q
      ? "order-2 mt-4 flex min-h-0 min-w-[32rem] flex-1 flex-col gap-2"
      : "order-1 mt-2 flex min-h-[22rem] flex-1 flex-col gap-2";
  return c.jsx(Ho.Provider, {
    value: activeTheme,
    children: c.jsxs("div", {
      ref: Ne,
      "data-visualiser-root": !0,
      className: `${activeTheme === "dark" ? "dark" : ""} relative flex h-full overflow-hidden overscroll-none w-full flex-col bg-[var(--vis-bg)]`,
      style: xa,
      children: [
        u
          ? c.jsx(jf, {
              phaserRef: h,
              assetBaseUrl: i,
              replay: S,
              turn: T,
              maxTurn: A,
              playing: I,
              speed: k,
              botStepMode: Q,
              subStep: Y,
              maxSubSteps: ce,
              onPrev: Bt,
              onNext: Mt,
              onPlayPause: qt,
              onSpeedUp: gt,
              onSlowDown: Zt,
              onToggleBotStepMode: ks,
              onSliderChange: Tn,
              gameState: $,
              matchData: oe,
              swapTeams: pe,
              selectedGameNumber: Fe,
              loadingGame: we,
              onSelectGame: r ? Gt : void 0,
              revealedGames: Ke,
              tournamentName: d,
              roundName: p,
              hoveredTile: null,
              selectedTile: D,
              showAllIndicators: ue,
              onToggleShowAllIndicators: cr,
              theme: activeTheme,
            })
          : c.jsxs(c.Fragment, {
              children: [
                c.jsxs("main", {
                  className: ba,
                  children: [
                    c.jsxs("div", {
                      className: va,
                      children: [
                        c.jsxs("div", {
                          className:
                            "relative aspect-square w-full overflow-hidden rounded-2xl border border-[var(--vis-border)]",
                          children: [
                            c.jsx(Uo, {
                              ref: h,
                              assetBaseUrl: i,
                              theme: activeTheme,
                            }),
                            c.jsxs("div", {
                              className:
                                "absolute bottom-3 right-3 flex flex-col gap-1",
                              children: [
                                [
                                  { label: "+", title: "Zoom in", factor: 1.2 },
                                  {
                                    label: "−",
                                    title: "Zoom out",
                                    factor: 1 / 1.2,
                                  },
                                ].map(({ label: _, title: V, factor: ke }) =>
                                  c.jsx(
                                    "button",
                                    {
                                      title: V,
                                      onClick: () =>
                                        h.current?.getScene()?.adjustZoom(ke),
                                      className:
                                        "flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--vis-border-2)] bg-[var(--vis-bg-panel-80)] text-sm font-bold text-[var(--vis-text-2)] backdrop-blur-sm hover:border-[#ffbf40] hover:text-[#ffbf40]",
                                      children: _,
                                    },
                                    _,
                                  ),
                                ),
                                c.jsx("button", {
                                  title: "Reset zoom",
                                  onClick: () =>
                                    h.current?.getScene()?.resetZoom(),
                                  className:
                                    "flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--vis-border-2)] bg-[var(--vis-bg-panel-80)] text-[10px] font-semibold text-[var(--vis-text-2)] backdrop-blur-sm hover:border-[#ffbf40] hover:text-[#ffbf40]",
                                  children: "⊡",
                                }),
                              ],
                            }),
                          ],
                        }),
                        c.jsx(Hl, {
                          replay: S,
                          turn: T,
                          maxTurn: A,
                          playing: I,
                          speed: k,
                          botStepMode: Q,
                          subStep: Y,
                          maxSubSteps: ce,
                          onPrev: Bt,
                          onNext: Mt,
                          onPlayPause: qt,
                          onSliderChange: Tn,
                          onTurnInput: lr,
                          onSpeedUp: gt,
                          onSlowDown: Zt,
                          onToggleBotStepMode: ks,
                        }),
                      ],
                    }),
                    !q &&
                      c.jsx("div", {
                        className: "order-2 w-full",
                        style: { minHeight: "42dvh" },
                        children: c.jsx(Fl, {
                        replay: S,
                        loading: C,
                        fileName: R,
                        turn: T,
                        maxTurn: A,
                        gameState: $,
                        onFileUpload: Je,
                        onFileDrop: ht,
                        matchData: oe,
                        selectedGameNumber: Fe,
                        loadingMatch: le,
                        loadingGame: we,
                        matchError: Ue,
                        onLoadMatch: r ? (_) => mt(_) : void 0,
                        onSelectGame: r ? Gt : void 0,
                        initialMatchId: e,
                        selectedTile: D,
                        hoveredTile: H,
                        showAllIndicators: ue,
                        onToggleShowAllIndicators: cr,
                        tournamentMode: u,
                        revealedGames: Ke,
                        swapTeams: pe,
                        }),
                      }),
                    q &&
                      c.jsx("div", {
                        className: "order-1 block w-64 flex-shrink-0",
                        children: c.jsx(Vo, {
                        replay: S,
                        loading: C,
                        fileName: R,
                        turn: T,
                        maxTurn: A,
                        gameState: $,
                        onFileUpload: Je,
                        onFileDrop: ht,
                        matchData: oe,
                        selectedGameNumber: Fe,
                        loadingMatch: le,
                        loadingGame: we,
                        matchError: Ue,
                        onLoadMatch: r ? (_) => mt(_) : void 0,
                        onSelectGame: r ? Gt : void 0,
                        initialMatchId: e,
                        tournamentMode: u,
                        revealedGames: Ke,
                        swapTeams: pe,
                        }),
                      }),
                    q &&
                      c.jsx("div", {
                        className: "order-3 block w-72 flex-shrink-0",
                        children: c.jsx(Ll, {
                        selectedTile: D,
                        hoveredTile: H,
                        showAllIndicators: ue,
                        onToggleShowAllIndicators: cr,
                        swapTeams: pe,
                        }),
                      }),
                  ],
                }),
                D &&
                  !q &&
                  c.jsx(Yo, {
                    selectedTile: D,
                    hoveredTile: de ? H : null,
                    swapTeams: pe,
                  }),
              ],
            }),
      ],
    }),
  });
}
const Pt = new URLSearchParams(window.location.search),
  Ap = Pt.get("replayUrl") ?? void 0,
  Op = Pt.get("matchId") ?? void 0,
  Bo = Pt.get("game"),
  jp = Bo ? parseInt(Bo, 10) : void 0,
  _r = Pt.get("apiUrl") ?? void 0,
  Mo = Pt.get("token") ?? void 0,
  Ip = Pt.get("assetBaseUrl") ?? void 0,
  Np = Pt.get("tournament") === "1",
  Pp = Pt.get("theme") === "light" ? "light" : "dark";
let ma, ga;
if (_r && Mo) {
  const e = { Authorization: `Bearer ${Mo}` };
  ((ma = async (t) => {
    const n = await fetch(`${_r}/api/matches/${t}`, { headers: e });
    if (!n.ok) throw new Error("Failed to fetch match");
    return n.json();
  }),
    (ga = async (t, n) => {
      const r = await fetch(
        `${_r}/api/matches/replay?matchId=${encodeURIComponent(t)}&game=${n}`,
        { headers: e },
      );
      if (!r.ok) throw new Error("Failed to get replay URL");
      const { url: s } = await r.json(),
        o = await fetch(s);
      if (!o.ok) throw new Error(`Failed to download replay: HTTP ${o.status}`);
      return o.arrayBuffer();
    }));
}
Za.createRoot(document.getElementById("root")).render(
  c.jsx(m.StrictMode, {
    children: c.jsx(kp, {
      initialReplayUrl: Ap,
      initialMatchId: Op,
      initialGameNumber: jp,
      fetchMatch: ma,
      fetchReplay: ga,
      assetBaseUrl: Ip,
      tournamentMode: Np,
      theme: Pp,
    }),
  }),
);
