// Who gets which alert, on the real screens: Ravi never sees a reception-PC alert, Meena never
// sees an alert on Ravi's computer, and the IT contact's panel shows every alert as it happens.
// Needs the backend with ACTIONS=1 serving the built app; the supplier story also needs SIMULATE=1.
// They press Reset, so never point them at a live demo.
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

test("reception-PC password attack: Meena and IT are told, Ravi's phone stays clear", async ({ browser, request }) => {
  const meena = await device(browser, PHONE, "/staff/1");
  const ravi = await device(browser, PHONE, "/staff/2");
  const it = await device(browser, LAPTOP, "/it");
  await expect(it.page.getByText("Every alert at the clinic appears here the moment it happens.")).toBeVisible();

  await backstage(request, "replay/password_guessing");

  // Meena: the card and the attack note.
  await expect(meena.page.getByRole("heading", { name: /guessing the password on RECEPTION-PC/ })).toBeVisible();
  await expect(meena.page.getByRole("article", { name: "Attack notification" })).toBeVisible();
  // Suresh: the ticket is there before anyone has called.
  await expect(it.page.getByRole("heading", { name: /guessing on RECEPTION-PC/i })).toBeVisible();
  await expect(it.page.getByText("Open · nobody has called yet")).toBeVisible();

  // Meena says "That was me" and it happens again (the screenshot's case): still nothing for Ravi.
  await meena.page.getByRole("button", { name: /That was me/ }).click();
  await backstage(request, "replay/password_guessing");
  await expect(meena.page.getByText(/It happened again after "That was me"/)).toBeVisible();
  await expect(it.page.getByRole("heading", { name: /guessing on RECEPTION-PC/i })).toBeVisible();

  // Ravi, after both rounds (his phone polls every 2 s): all clear, no note, nothing in History.
  await ravi.page.reload();
  await expect(ravi.page.getByRole("heading", { name: "All clear" })).toBeVisible();
  await expect(ravi.page.getByRole("heading", { name: /guessing the password/ })).toHaveCount(0);
  await expect(ravi.page.getByRole("article", { name: /notification/i })).toHaveCount(0);
  await ravi.page.goto("/staff/2/history");
  await expect(ravi.page.getByRole("heading", { name: "Nothing yet" })).toBeVisible();

  for (const d of [meena, ravi, it]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("escalation: Ravi, the backup approver, gets a Block button that works, but not the card", async ({ browser, request }) => {
  const ravi = await device(browser, PHONE, "/staff/2");
  const owner = await device(browser, LAPTOP, "/owner");
  await backstage(request, "replay/password_guessing");
  await expect(owner.page.getByText("Your decision needed")).toBeVisible();

  // Dr. Rao doesn't answer for 5 minutes (no standing rule): Ravi is asked to decide.
  await backstage(request, "skip", { minutes: 5 });
  const note = ravi.page.getByRole("article", { name: "Notification" }).filter({ hasText: "hasn't answered" });
  await expect(note).toBeVisible({ timeout: 15_000 });
  await expect(note).toContainText("RECEPTION-PC");
  await expect(ravi.page.getByRole("heading", { name: "All clear" })).toBeVisible();     // no card for him

  await note.getByRole("button", { name: /^Block 192\.168\.1\.57 for 60 minutes$/ }).click();
  await expect(note.getByRole("button", { name: /^Blocked/ })).toBeDisabled();
  await expect(owner.page.getByText(/Blocked · approved by Ravi/)).toBeVisible();

  for (const d of [ravi, owner]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("mission control's people panel only shows progress for the person whose computer it is", async ({ browser, request }) => {
  const mission = await device(browser, { width: 1440, height: 900 }, "/mission");
  const meena = await device(browser, PHONE, "/staff/1");
  await backstage(request, "replay/password_guessing");
  await meena.page.getByRole("button", { name: /Don't log in from RECEPTION-PC/ }).click();

  const person = (name) => mission.page.locator(".mc-person").filter({ hasText: name });
  await expect(person("Meena")).toContainText("1 of 3 steps done");
  await expect(person("Ravi")).toContainText("All quiet");

  for (const d of [mission, meena]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});

test("supplier fraud lands on Ravi's computer: Ravi, the owner and IT see it, Meena doesn't", async ({ browser, request }) => {
  test.skip(!flags.SIMULATE, "start the backend with SIMULATE=1");
  const ravi = await device(browser, PHONE, "/staff/2");
  const meena = await device(browser, PHONE, "/staff/1");
  const it = await device(browser, LAPTOP, "/it");

  await backstage(request, "simulate/supplier_bank_fraud");
  await expect(ravi.page.getByRole("heading", { name: /pay a supplier's new bank account/ })).toBeVisible({ timeout: 15_000 });
  await expect(ravi.page.getByRole("article", { name: "Attack notification" })).toBeVisible();
  await expect(it.page.getByRole("heading", { name: /supplier email asks to change their bank details/i })).toBeVisible();
  await expect(it.page.getByText("FILE-SERVER", { exact: true }).first()).toBeVisible();
  await expect(meena.page.getByRole("heading", { name: "All clear" })).toBeVisible();
  await expect(meena.page.getByRole("article", { name: /notification/i })).toHaveCount(0);

  for (const d of [ravi, meena, it]) {
    expect(d.errors).toEqual([]);
    await d.close();
  }
});
