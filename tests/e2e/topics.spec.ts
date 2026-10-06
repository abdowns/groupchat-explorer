import { test, expect } from "@playwright/test";

test("topic prevalence, significant conversations, and era arcs remain source-linked", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const message = {
    id: "source",
    source_id: "source",
    chat_id: "fictional",
    person_id: "a",
    ts: 1704326400,
    text: "I submitted my college application and finished the admissions essay.",
    kind: "message",
    parts: [],
    edits: [],
    words: 12,
    reaction_count: 0,
    reactions: [],
    attachments: [],
  };
  const era = {
    id: "era",
    name: "College applications",
    start: 1704326400,
    end: 1707004800,
    summary: "A fictional application arc",
    sources: ["source"],
    manual: 0,
  };
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let data: unknown = [];
    if (url.pathname.endsWith("/config")) data = { session_token: "synthetic" };
    else if (url.pathname === "/api/v1/workspaces")
      data = [
        {
          id: "synthetic",
          name: "Fictional group",
          people: [{ id: "a", name: "Alex", color: "#638b70", aliases: "[]" }],
          coverage: {},
          demo: true,
        },
      ];
    else if (url.pathname.endsWith("/settings")) data = { timezone: "UTC" };
    else if (url.pathname.endsWith("/jobs/events")) {
      await route.fulfill({
        contentType: "text/event-stream",
        body: "data: []\n\n",
      });
      return;
    } else if (url.pathname.endsWith("/analytics/overview")) {
      await route.abort();
      return;
    } else if (url.pathname.endsWith("/timeline"))
      data = {
        eras: [era],
        events: [],
        activity: [{ month: "2024-01", count: 4 }],
        milestones: [],
        semantic_eras_ready: true,
      };
    else if (url.pathname.endsWith("/topics"))
      data = {
        ready: true,
        topics: [
          {
            id: 1,
            label: "College applications",
            count: 2,
            terms: ["college", "applications", "essays"],
            sources: ["source"],
          },
        ],
        trend: [{ topic_id: 1, month: "2024-01", count: 2, share: 0.5 }],
        totals: [{ month: "2024-01", total: 4 }],
      };
    else if (url.pathname.endsWith("/topics/1/conversations"))
      data = {
        topic: { id: 1, label: "College applications" },
        conversations: [
          {
            id: "conversation",
            start: 1704326400,
            topic_messages: 2,
            participants: 2,
            conversation_messages: 4,
            preview: message.text,
            sources: ["source"],
          },
        ],
      };
    else if (url.pathname.endsWith("/messages")) {
      if (url.searchParams.has("session"))
        expect(url.searchParams.get("session")).toBe("conversation");
      else expect(url.searchParams.get("start")).toBe(String(era.start));
      data = { items: [message], next_cursor: null };
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/");
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Topics & search", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "Topic prevalence over time" }),
  ).toBeVisible();
  await expect(page.getByLabel("Topic prevalence metric")).toHaveValue("share");
  await page.getByLabel("Topic prevalence metric").selectOption("count");
  await page
    .getByRole("button", { name: "Explore topic & conversations" })
    .click();
  await expect(
    page.getByText("Significant conversations: College applications"),
  ).toBeVisible();
  await page.locator(".session-row").first().click();
  await expect(page.locator(".drawer .message-card").first()).toContainText(
    "admissions essay",
  );
  await page.getByRole("button", { name: "Close messages" }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "Timeline", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "Group chat era timeline" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Group chat era timeline" }).locator("svg"),
  ).toBeVisible();
  const arc = page
    .getByRole("img", { name: "Group chat era timeline" })
    .locator('svg path[fill="#df7253"]');
  await expect(arc).toHaveCount(1);
  await page.screenshot({
    path: "/tmp/gcapp-arcs-preview.png",
    fullPage: true,
  });
  await arc.click();
  await expect(
    page.getByRole("dialog", { name: "College applications" }),
  ).toBeVisible();
  await expect(page.locator(".drawer .message-card").first()).toContainText(
    "admissions essay",
  );
  expect(errors).toEqual([]);
});
