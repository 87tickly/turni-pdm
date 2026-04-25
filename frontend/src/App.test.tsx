import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "@/App";

describe("App", () => {
  it("mostra il titolo Colazione", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /colazione/i })).toBeInTheDocument();
  });

  it("indica lo Sprint corrente nel sottotitolo", () => {
    render(<App />);
    expect(screen.getByText(/sprint 0\.2/i)).toBeInTheDocument();
  });
});
