import { test, expect } from "@playwright/test";

test("semantic prevalence ranks authors and opens filtered source messages", async ({
  page,
}) => {
  let analyzed = false;
  let sourcePerson = "";
  const people = [
    { id: "a", name: "Alex", color: "#638b70", aliases: "[]" },
    { id: "b", name: "Blair", color: "#df7253", aliases: "[]" },
  ];
  const message = {
    id: "match",
    source_id: "match",
    chat_id: "synthetic",
    person_id: "a",
    ts: 1704151800,
    text: "I met my crush for dinner last night.",
    kind: "message",
    parts: [],
    edits: [],
    words: 9,
    reaction_count: 0,
    reactions: [],
    attachments: [],
  };
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown = {};
    if (path.endsWith("/config")) data = { session_token: "synthetic" };
    else if (path === "/api/v1/workspaces")
      data = [
        {
          id: "synthetic",
          name: "Fictional group",
          created: "2024-01-01",
          people,
          coverage: {},
          demo: true,
        },
      ];
    else if (path.endsWith("/jobs/events")) {
      await route.fulfill({
        contentType: "text/event-stream",
        body: "data: []\n\n",
      });
      return;
    } else if (path.endsWith("/timeline"))
      data = { eras: [], events: [], activity: [] };
    else if (path.endsWith("/settings"))
      data = { timezone: "America/Los_Angeles" };
    else if (path.endsWith("/analytics/overview")) {
      await route.abort(); // This test exercises only the semantic view.
      return;
    } else if (path.endsWith("/words"))
      data = {
        occurrences: 0,
        matching_messages: 0,
        people: [],
        trend: [],
        variants: {},
        messages: [],
      };
    else if (path.endsWith("/semantic-words/analyze")) {
      expect(route.request().postDataJSON()).toEqual({
        q: "girls",
        threshold: 0.35,
      });
      analyzed = true;
      data = { status: "queued", job_id: "synthetic-job" };
    } else if (path.endsWith("/semantic-words"))
      data = analyzed
        ? {
            ready: true,
            status: "complete",
            matching_messages: 1,
            total_messages: 4,
            people: [
              { ...people[0], matches: 1, messages: 2, per_1000: 500 },
              { ...people[1], matches: 0, messages: 2, per_1000: 0 },
            ],
            trend: [{ date: "2024-01", count: 1 }],
            messages: [message],
          }
        : { ready: false, status: "not_analyzed" };
    else if (path.endsWith("/semantic-matches")) {
      sourcePerson = url.searchParams.get("person") ?? "";
      expect(url.searchParams.get("q")).toBe("girls");
      expect(url.searchParams.get("threshold")).toBe("0.35");
      data = { items: [message], next_cursor: null };
    } else data = [];
    await route.fulfill({ json: data });
  });
  await page.goto("/");
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Words & phrases", exact: true })
    .click();
  await page.getByLabel("Word matching mode").selectOption("semantic");
  await page.getByLabel("Word or phrase").fill("girls");
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await page
    .getByRole("button", { name: "Analyze meaning", exact: true })
    .click();
  await expect(page.getByText("Who talks about “girls” most?")).toBeVisible();
  await expect(page.getByLabel("Semantic ranking metric")).toHaveValue(
    "per_1000",
  );
  await expect(page.locator(".bar-row").first()).toContainText("500.00");
  await expect(page.locator(".bar-row").first()).toContainText("2 messages");
  await page.locator(".bar-row").first().click();
  await expect(
    page.getByRole("dialog", { name: "Alex talking about “girls”" }),
  ).toBeVisible();
  await expect(page.locator(".drawer .message-card").first()).toContainText(
    "my crush",
  );
  expect(sourcePerson).toBe("a");
});
