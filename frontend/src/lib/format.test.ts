import { describe, expect, it } from "vitest";
import { money, percent, titleCase } from "./format";

describe("formatters", () => {
  it("renders missing money as an em dash", () => {
    expect(money(null)).toBe("—");
    expect(money(12.5)).toContain("12.50");
  });

  it("does not invent a percentage", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0.25)).toBe("25.0%");
  });

  it("reads status codes as words", () => {
    expect(titleCase("awaiting_review")).toBe("awaiting review");
  });
});
