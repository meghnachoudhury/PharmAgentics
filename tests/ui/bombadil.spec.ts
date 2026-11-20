// Bombadil explores the running app (dev sign-in, every role) and checks these after every action it takes.
// Run with: uv run python tests/ui/run_bombadil.py
import { always, extract } from "@antithesishq/bombadil";

export * from "@antithesishq/bombadil/browser/defaults";

const visibleText = extract((state) => state.document.body?.innerText ?? "");
const accountRole = extract((state) =>
  state.document.querySelector("header")?.innerText ?? "");

// CLAUDE.md: say "competitive intelligence", never "surveillance".
export const neverSaysSurveillance = always(() => !/surveillance/i.test(visibleText.current));

// Testing scaffolding stays out of the product: no "UAT" names, no persona codes.
export const noTestingScaffolding = always(() => !/\bUAT\b|\bP[1-4]\b/.test(visibleText.current));

// Participants are pseudonymous in storage; a pseudonym must never reach the screen.
export const noPseudonymOnScreen = always(() => !/\bu-[0-9a-f]{12}\b/.test(visibleText.current));

// Broken rendering of a value.
export const noBrokenValues = always(() => !/\bNaN\b|\bundefined\b|\[object Object\]|\bInfinity\b/.test(visibleText.current));

// The server strips evidence from the leadership view; a leader must never see the evidence panel.
export const leadersSeeNoEvidence = always(() =>
  !/Brand (Director|Manager)/.test(accountRole.current) ||
  !/Governed evidence|Source records/.test(visibleText.current));
