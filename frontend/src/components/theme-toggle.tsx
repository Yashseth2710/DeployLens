"use client";

import { useTheme } from "next-themes";

import { Button } from "@/components/button";

/**
 * Dark is the pressroom, light is the bench, and the control names the room you
 * are moving to. Which label shows is decided in CSS off the theme attribute
 * rather than by waiting for mount, so the button is correct in the first
 * paint instead of flickering into place.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Button
      variant="quiet"
      size="compact"
      aria-label="Switch between the pressroom and the bench"
      onClick={() => setTheme(resolvedTheme === "light" ? "dark" : "light")}
    >
      <span className="hidden [html[data-theme='light']_&]:inline">Pressroom</span>
      <span className="[html[data-theme='light']_&]:hidden">Bench</span>
    </Button>
  );
}
