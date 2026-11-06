#!/usr/bin/env node
// Ruleset guardrail: the branch protection this repo ships must actually protect.
//
// `docs/50-deployment/rebuild/main-ruleset.json` is not documentation. It is the
// artifact applied verbatim at bootstrap - `gh api repos/vxture/<repo>/rulesets
// --method POST --input <this file>` - so every product repo created from vxtpl
// inherits exactly what it says. That makes an error here different in kind from
// an error in a normal file: it does not affect one repo, it affects every repo
// created after it.
//
// It has already happened once. The file carried
//
//     "bypass_actors": [{ "actor_id": 5, "RepositoryRole", "bypass_mode": "always" }]
//
// - actor_id 5 is the repo admin role, and `always` means every situation,
// including a direct push. So for any admin, PR-required, the five status checks,
// linear history, no force-push and no branch deletion were all suggestions. It
// surfaced by accident in another repo when a commit pushed straight to main
// succeeded, against a CLAUDE.md that said direct pushes were blocked. Checking
// the API afterwards found the same bypass on every repo in the org, because they
// were all bootstrapped from this file (vxtpl#37).
//
// The live rulesets were fixed. This file was not, so the next repo created would
// have inherited it again. That is the failure this check exists to prevent: not
// the original mistake, but its reintroduction.
//
// TWO ASSERTIONS, both from CLAUDE.md's rigid zone:
//
//   1. bypass_actors is empty. A protection with an exemption for the people most
//      able to use it is a note, not a control.
//   2. The five required contexts are all present. "Never remove a check from the
//      required set" - a check that stops being required stops being a gate, and
//      the removal looks like a small diff.
//
// It does not check the live ruleset on GitHub: that needs a token and a network
// call, and a guardrail that can fail because an API was slow teaches people to
// ignore it. Compare the two by hand when bootstrapping - the checklist says so.

import { readFileSync } from "node:fs";

const STRICT = process.argv.includes("--strict");
const FILE = "docs/50-deployment/rebuild/main-ruleset.json";

/** The authoritative set. Renaming a CI job to something not in this list breaks protection. */
const REQUIRED_CONTEXTS = ["quality-gate", "build", "test-coverage", "audit", "gitleaks"];

const problems = [];

let ruleset;
try {
  ruleset = JSON.parse(readFileSync(FILE, "utf8"));
} catch (err) {
  console.error(`[ruleset] cannot read ${FILE}: ${err.message}`);
  console.error(`\nThis file is applied verbatim at bootstrap. If it is gone or malformed,\nthe next repo created from vxtpl has no branch protection at all.`);
  process.exit(STRICT ? 1 : 0);
}

// 1. No bypass.
const bypass = ruleset.bypass_actors ?? [];
if (bypass.length > 0) {
  problems.push(
    `bypass_actors is not empty - ${bypass.length} actor(s) can ignore every rule below:\n` +
      bypass
        .map((a) => `      actor_id=${a.actor_id} type=${a.actor_type} mode=${a.bypass_mode}`)
        .join("\n") +
      `\n    An exemption for the role most able to use it makes this a note, not a control.`,
  );
}

// 2. Every required check still required.
const checksRule = (ruleset.rules ?? []).find((r) => r.type === "required_status_checks");
if (!checksRule) {
  problems.push(`no required_status_checks rule - nothing gates a merge`);
} else {
  const declared = (checksRule.parameters?.required_status_checks ?? []).map((c) => c.context);
  const dropped = REQUIRED_CONTEXTS.filter((c) => !declared.includes(c));
  if (dropped.length > 0) {
    problems.push(
      `required contexts missing: ${dropped.join(", ")}\n` +
        `    declared: ${declared.join(", ") || "(none)"}\n` +
        `    A check that stops being required stops being a gate.`,
    );
  }
  if (checksRule.parameters?.strict_required_status_checks_policy !== true) {
    problems.push(
      `strict_required_status_checks_policy is not true - a branch can merge with checks\n` +
        `    that passed against an older base, which is how a green PR lands a red main.`,
    );
  }
}

// 3. The structural rules CLAUDE.md calls non-negotiable.
for (const [type, why] of [
  ["pull_request", "direct pushes to main would be allowed"],
  ["deletion", "main could be deleted"],
  ["non_fast_forward", "main could be force-pushed"],
  ["required_linear_history", "merge commits could land, breaking the squash-only history"],
]) {
  if (!(ruleset.rules ?? []).some((r) => r.type === type)) {
    problems.push(`missing rule "${type}" - ${why}`);
  }
}

if (problems.length === 0) {
  console.log(
    `[ruleset] OK - no bypass actors, ${REQUIRED_CONTEXTS.length} required contexts, structural rules present.`,
  );
  process.exit(0);
}

console.error(`[ruleset] ${problems.length} problem(s) in ${FILE}:\n`);
for (const p of problems) console.error(`  - ${p}\n`);
console.error(
  `This file is applied verbatim to every repo bootstrapped from vxtpl, so a weakened\n` +
    `protection here is inherited rather than contained. See vxtpl#37.`,
);
process.exit(STRICT ? 1 : 0);
