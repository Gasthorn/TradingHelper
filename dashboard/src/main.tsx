import { render } from "preact";

import { App } from "./App";

const root = document.getElementById("app");
if (root === null) {
  throw new Error("Élément #app introuvable dans index.html");
}
render(<App />, root);
