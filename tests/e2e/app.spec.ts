import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const data = await (
    await request.get("http://127.0.0.1:8765/api/v1/workspaces")
  ).json();
  if (!data.length) {
    const c = await (
      await request.get("http://127.0.0.1:8765/api/v1/config")
    ).json();
    await request.post("http://127.0.0.1:8765/api/v1/demo", {
      headers: { "X-Session-Token": c.session_token },
      data: {},
    });
  }
});

test("all views render without browser errors; archive statistics open source messages", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByText("Messages sent", { exact: true })).toBeVisible();
  await page.screenshot({ path: "/tmp/gcapp-overview.png", fullPage: true });
  await page.getByText("Messages sent", { exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Messages sent" }),
  ).toBeVisible();
  await expect(page.locator(".drawer .message-card").first()).toBeVisible();
  await page.getByRole("button", { name: "Close messages" }).click();
  for (const [label, title] of [
    ["Timeline", "The chapters"],
    ["People", "Select a member"],
    ["Reactions", "The crowd favorites"],
    ["Words & phrases", "Who owns"],
    ["Conversations", "Who starts things?"],
    ["Topics & search", "Ask your archive"],
    ["Group lore", "A RUNNING BIT"],
    ["Media & links", "Your shared corner"],
    ["Recaps & games", "How well do you know"],
    ["Settings & analysis", "Make yourself at home"],
  ]) {
    await page
      .locator(".sidebar")
      .getByRole("button", { name: label, exact: true })
      .click();
    await expect(page.getByText(title, { exact: false }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("word matching, member filtering, identity profile and games", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Words & phrases", exact: true })
    .click();
  await page.getByLabel("Word or phrase").fill("the council");
  await page.getByLabel("Word matching mode").selectOption("phrase");
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await expect(page.getByText("Who owns “the council”?")).toBeVisible();
  await expect(page.locator(".message-card").first()).toContainText(
    "the council",
  );
  await page.getByLabel("Filter by member").selectOption({ label: "Alex" });
  await expect(page.locator(".message-card").first()).toContainText("Alex");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "People", exact: true })
    .click();
  await page.locator(".person-card").first().click();
  await expect(page.getByText("Longest streak", { exact: true })).toBeVisible();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Recaps & games", exact: true })
    .click();
  for (const kind of ["Who said it?", "Finish the quote", "Guess the year"]) {
    await page.getByRole("button", { name: kind, exact: true }).click();
    await page
      .getByRole("button", { name: "Play a round", exact: true })
      .click();
    await expect(page.locator(".game-options button").first()).toBeVisible();
    await page.locator(".game-options button").first().click();
    await expect(
      page.getByRole("button", { name: "Reveal the conversation" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Reveal the conversation" }).click();
    await expect(page.locator(".drawer .message-card.highlight")).toBeVisible();
    await page.getByRole("button", { name: "Close messages" }).click();
  }
});

test("editable eras, source conversations and responsive navigation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Timeline", exact: true })
    .click();
  await page.getByRole("button", { name: "Add an era" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a chapter" });
  await dialog.getByLabel("Name", { exact: true }).fill("Test chapter");
  await dialog.getByLabel("Start", { exact: true }).fill("2022-01-01");
  await dialog.getByLabel("End", { exact: true }).fill("2022-12-31");
  await dialog.getByRole("button", { name: "Save chapter" }).click();
  await expect(
    page.getByRole("heading", { name: "Test chapter" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit Test chapter" }).click();
  await page.getByRole("button", { name: "Delete chapter" }).click();
  await expect(page.getByRole("heading", { name: "Test chapter" })).toHaveCount(
    0,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(page.getByText("Messages sent", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "/tmp/gcapp-mobile.png", fullPage: true });
});

test("lore journey, media context, recap export and editable awards", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Group lore", exact: true })
    .click();
  await page.getByRole("button", { name: "Trace the lore" }).first().click();
  const lore = page.getByRole("dialog", { name: "A bit through the years" });
  await expect(lore.getByText("Related conversation candidates")).toBeVisible({
    timeout: 20000,
  });
  await lore
    .getByRole("button", { name: "Open every matching conversation" })
    .click();
  await expect(page.locator(".drawer .message-card").first()).toBeVisible();
  await page.getByRole("button", { name: "Close messages" }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Media & links", exact: true })
    .click();
  await expect(page.locator(".media-card img").first()).toBeVisible();
  await page
    .locator(".media-card")
    .filter({ has: page.locator("img") })
    .first()
    .getByRole("button", { name: "View context" })
    .click();
  await expect(page.locator(".drawer .message-card.highlight")).toBeVisible();
  await page.getByRole("button", { name: "Close messages" }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Recaps & games", exact: true })
    .click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save recap card" }).click();
  expect((await download).suggestedFilename()).toBe("group-chat-recap.png");
  await page.getByRole("button", { name: "Add your own" }).click();
  let dialog = page.getByRole("dialog", {
    name: "An award only your group would give",
  });
  await dialog.getByLabel("Title", { exact: true }).fill("Test champion");
  await dialog.getByLabel("The reason").fill("For testing the archive");
  await dialog.getByRole("button", { name: "Save award" }).click();
  await page
    .getByRole("button", { name: "Edit Test champion", exact: true })
    .click();
  dialog = page.getByRole("dialog", {
    name: "An award only your group would give",
  });
  await dialog.getByLabel("Title", { exact: true }).fill("Updated champion");
  await dialog.getByRole("button", { name: "Save award" }).click();
  await expect(
    page.getByRole("heading", { name: "Updated champion" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit Updated champion", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete award", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Updated champion" }),
  ).toHaveCount(0);
});
