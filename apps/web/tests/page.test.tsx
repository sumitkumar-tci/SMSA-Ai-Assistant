import { render, screen } from "@testing-library/react";
import HomePage from "../app/page";

describe("HomePage", () => {
  it("renders heading", () => {
    render(<HomePage />);
    expect(
      screen.getByText("SMSA AI Assistant - Tracking")
    ).toBeInTheDocument();
  });
});

