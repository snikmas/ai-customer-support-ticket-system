import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { fieldIssues, validationIssues } from "./validation";

describe("validation details mapping", () => {
  it("maps structured 422 body locations to their fields", () => {
    const error = new ApiError("Invalid request data", 422, "validation_error", [
      { type: "value_error", loc: ["body", "email"], msg: "value is not a valid email address" },
      { type: "missing", loc: ["body", "phone"], msg: "Field required" },
    ]);

    const issues = validationIssues(error);

    expect(issues).toHaveLength(2);
    expect(fieldIssues(issues, "body")).toEqual({
      email: "Enter a valid email address.",
      phone: "Enter a valid phone number.",
    });
  });

  it("maps query locations separately from body locations", () => {
    const error = new ApiError("Invalid request data", 422, "validation_error", [
      { type: "less_than_equal", loc: ["query", "priority"], msg: "Input should be less than or equal to 4" },
    ]);

    const issues = validationIssues(error);

    expect(fieldIssues(issues, "query")).toEqual({
      priority: "Input should be less than or equal to 4.",
    });
    expect(fieldIssues(issues, "body")).toEqual({});
  });

  it("falls back safely for non-JSON or shapeless errors", () => {
    expect(validationIssues(new ApiError("Request failed", 500, "internal_server_error"))).toEqual([]);
    expect(validationIssues(new ApiError("Invalid request data", 422, "validation_error", null))).toEqual([]);
    expect(validationIssues(new Error("plain"))).toEqual([]);
    expect(validationIssues(new ApiError("Invalid request data", 422, "validation_error", ["oops"]))).toEqual([]);
  });
});
