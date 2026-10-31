// The three v4 drills, end to end: learning mode (a drill where Ravi gets his own choices) and
// test mode (an attack script that the team stops by ticking the right step on a card).
// Needs the backend with ACTIONS=1 serving the built app; the test-mode stories also need
// SIMULATE=1 and are skipped without it. They press Reset, so never point them at a live demo.
import { expect, test } from "@playwright/test";

const PHONE = { width: 390, height: 844 };
const LAPTOP = { width: 1280, height: 900 };

async function backstage(request, path, data) {
  const r = await request.post(`/api/demo/${path}`, data ? { data } : undefined);
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}

async function device(browser, viewport, path) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(path);
  return { page, errors, close: () => context.close() };
}

let flags = {};
test.beforeEach(async ({ request }) => {
  flags = (await (await request.get("/api/status")).json()).flags;
  test.skip(!flags.ACTIONS, "start the backend with ACTIONS=1");
  await backstage(request, "reset");
});

test("supplier drill: Ravi gets his own choices and Meena waits that moment out", async ({ browser }) => {
  const owner = await device(browser, LAPTOP, "/owner/drill");
  await owner.page.getByLabel("Scenario").selectOption("supplier_bank_fraud");
  await owner.page.getByRole("button", { name: "Start team drill" }).click();
  const code = (await owner.page.locator(".mono").filter({ hasText: /^\d{4}$/ }).first().textContent()).trim();

  const meena = await device(browser, PHONE, `/staff/1/drill`);
  await meena.page.getByLabel("Drill code").fill(code);
  await meena.page.getByRole("button", { name: "Join as Meena" }).click();
  const ravi = await device(browser, PHONE, `/staff/2/drill`);
  await ravi.page.getByLabel("Drill code").fill(code);
  await ravi.page.getByRole("button", { name: "Join as Ravi" }).click();
  await expect(owner.page.getByText("3 joined")).toBeVisible();

  await owner.page.getByRole("button", { name: "Begin moment 1" }).click();
  await expect(ravi.page.getByText("MOMENT 1 / 4")).toBeVisible();
  // Ravi's payment choices are his alone.
  await expect(meena.page.getByText("MOMENT 1 / 4")).toBeVisible();
  await expect(meena.page.getByRole("button", { name: /Call the supplier on the number you already have/ })).toHaveCount(0);
  await ravi.page.getByRole("button", { name: /Call the supplier on the number you already have/ }).click();
  await expect(ravi.page.getByText("Nice call! +1 for the team")).toBeVisible();

  await expect(owner.page.getByRole("button", { name: "Next moment" })).toBeVisible();
  await owner.page.getByRole("button", { name: "End drill now" }).click();
  await expect(owner.page.getByRole("heading", { name: "Team result: 1 of 1" })).toBeVisible();

  for (const d of [owner, meena, ravi]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("test mode: Ravi checks by phone, the payment never happens, everyone sees who stopped it", async ({ browser, request }) => {
  test.skip(!flags.SIMULATE, "start the backend with SIMULATE=1");
  const ravi = await device(browser, PHONE, "/staff/2");
  const meena = await device(browser, PHONE, "/staff/1");
  const owner = await device(browser, LAPTOP, "/owner");

  await backstage(request, "simulate/supplier_bank_fraud");

  // The card reaches Ravi (not Meena), with the lookalike sender exactly as received.
  await expect(ravi.page.getByRole("heading", { name: /pay a supplier's new bank account/ })).toBeVisible({ timeout: 15_000 });
  await ravi.page.getByText("Details from the computer's log").click();
  await expect(ravi.page.getByText("accounts@shreelab-supplies.in")).toBeVisible();
  await expect(owner.page.getByRole("heading", { name: /supplier email asks to change their bank details/i })).toBeVisible();
  await expect(meena.page.getByRole("heading", { name: "All clear" })).toBeVisible();

  await ravi.page.getByRole("button", { name: /Don't pay\. Call the supplier/ }).click();
  await expect(ravi.page.getByRole("button", { name: /Don't pay\. Call the supplier/ })).toHaveAttribute("aria-pressed", "true");

  // Jump past the payment stage; the next ingest poll settles the run as contained.
  await backstage(request, "skip", { minutes: 5 });
  await expect(owner.page.getByText(/Practice attack · Attack stopped in/)).toBeVisible({ timeout: 15_000 });
  await expect(owner.page.getByText(/Ravi: check by calling back/)).toBeVisible();
  await expect(meena.page.getByText(/Practice attack · Attack stopped in/)).toBeVisible();
  await expect(owner.page.getByRole("heading", { name: /payment went to a possible scammer/i })).toHaveCount(0);

  for (const d of [ravi, meena, owner]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("test mode: nobody unplugs, the attack spreads, and the projector says what would have stopped it", async ({ browser, request }) => {
  test.skip(!flags.SIMULATE, "start the backend with SIMULATE=1");
  const mission = await device(browser, LAPTOP, "/mission");
  const meena = await device(browser, PHONE, "/staff/1");

  await backstage(request, "simulate/tech_support_call");
  await expect(meena.page.getByRole("heading", { name: /program that lets someone control this computer/ })).toBeVisible({ timeout: 15_000 });
  await expect(mission.page.getByRole("status").filter({ hasText: "ATTACK IN PROGRESS" })).toBeVisible();

  await backstage(request, "skip", { minutes: 5 });
  await expect(mission.page.getByText("The attack got through")).toBeVisible({ timeout: 15_000 });
  await expect(mission.page.getByText(/What would have stopped it: unplug the network/)).toBeVisible();

  for (const d of [mission, meena]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("the ? works inside a drill and tells the server which drill, and never offers the answer choices", async ({ browser, request }) => {
  const owner = await device(browser, LAPTOP, "/owner/drill");
  await owner.page.getByLabel("Scenario").selectOption("tech_support_call");
  await owner.page.getByRole("button", { name: "Start team drill" }).click();
  const code = (await owner.page.locator(".mono").filter({ hasText: /^\d{4}$/ }).first().textContent()).trim();

  const meena = await device(browser, PHONE, `/staff/1/drill`);
  await meena.page.getByLabel("Drill code").fill(code);
  await meena.page.getByRole("button", { name: "Join as Meena" }).click();
  await expect(owner.page.getByText("2 joined")).toBeVisible();
  await owner.page.getByRole("button", { name: "Begin moment 1" }).click();
  await expect(meena.page.getByText("MOMENT 1 / 4")).toBeVisible();

  // Lobby has no card, so no "?"; the moment does.
  const help = meena.page.getByRole("button", { name: /simpler words/i });
  await expect(help).toBeVisible();
  await help.click();
  const sheet = meena.page.getByRole("dialog");
  await expect(sheet.getByText("Moment 1")).toBeVisible();
  await expect(sheet.getByRole("checkbox")).toHaveCount(1);          // the situation only: no answer options
  await sheet.getByRole("checkbox").first().check();

  const sent = meena.page.waitForRequest((r) => r.url().includes("/interpreter/chat"));
  await sheet.getByRole("button", { name: "Rephrase 1 card" }).click();
  const body = (await sent).postDataJSON();
  expect(body.drill_code).toBe(code);
  expect(body.role).toBe("front_desk");
  // The answer buttons are untouched, and the result (or the "not enabled" note) shows under the moment.
  await expect(meena.page.getByText(/AI help isn't enabled here|Couldn't rephrase|In simpler words/).first()).toBeVisible();
  await expect(meena.page.getByRole("group", { name: "Answers" })).toBeVisible();

  // Owner's own drill screen has it too.
  await expect(owner.page.getByRole("button", { name: /simpler words/i })).toBeVisible();

  for (const d of [owner, meena]) {
    expect(d.errors.filter((e) => !e.startsWith("Failed to load resource"))).toEqual([]);
    await d.close();
  }
});

test("backstage always shows the attack simulation, and says when it is switched off", async ({ browser }) => {
  const bs = await device(browser, { width: 900, height: 1200 }, "/backstage");
  const card = bs.page.getByRole("region", { name: "Attack simulation" });
  await expect(card).toBeVisible();
  await expect(card.getByText(/Fake supplier bank details/)).toBeVisible();
  const plays = card.getByRole("button", { name: "Play" });
  if (flags.SIMULATE) {
    await expect(plays.first()).toBeEnabled();
    await expect(card.getByText(/switched off/)).toHaveCount(0);
  } else {
    await expect(plays.first()).toBeDisabled();
    await expect(card.getByText(/SIMULATE=1/)).toBeVisible();
  }
  expect(bs.errors).toEqual([]);
  await bs.close();
});
