import { afterEach, expect, it, vi } from "vitest";
import { api, display, setWriteKey } from "./api";
afterEach(() => {
  vi.unstubAllGlobals();
  setWriteKey("");
});
it("renders unknown values without fabricating zero", () => {
  expect(display(null)).toBe("—");
  expect(display(0)).toBe("0");
});
it("surfaces safe API errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({ ok: false, json: async () => ({ detail: "限流" }) }),
  );
  await expect(api("/x")).rejects.toThrow("限流");
});
it("sends explicitly configured write key only in header", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ id: 1 }) });
  vi.stubGlobal("fetch", fetcher);
  setWriteKey("test");
  await api("/tasks", { title: "x" });
  expect(fetcher.mock.calls[0][1].headers["X-API-Key"]).toBe("test");
  expect(fetcher.mock.calls[0][0]).not.toContain("test");
});
