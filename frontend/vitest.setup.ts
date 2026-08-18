import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// React Testing Library leaves each render mounted. Without this, a component that
// queries by role finds the previous test's copy as well as its own.
afterEach(cleanup);
