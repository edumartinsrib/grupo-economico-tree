import { expect, test } from "@playwright/test";

test("searches an entity and shows family aggregation between official groups", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Painel de grupos econômicos" })).toBeVisible();

  await page.getByLabel("Nome, CPF, CNPJ ou grupo").fill("Carlos Almeida");
  await expect(page.getByRole("button", { name: /CARLOS ALMEIDA/ }).first()).toBeVisible();

  await page.getByRole("button", { name: /CARLOS ALMEIDA/ }).first().click();

  await expect(page.getByText("GRUPO ALMEIDA OFICIAL").first()).toBeVisible();
  await expect(page.getByText("GRUPO SERVICOS MARIA").first()).toBeVisible();
  await expect(page.getByText("GRUPO CLINICA PAULA").first()).toBeVisible();
  await expect(page.getByText("Agregação familiar").first()).toBeVisible();

  await page.getByRole("button", { name: "Aproximar" }).click();
  await expect(page.getByText("102%")).toBeVisible();

  await expect(page.getByRole("heading", { name: "Empresas" })).toBeVisible();
  await expect(page.getByText("ALMEIDA HOLDING LTDA").first()).toBeVisible();
  await expect(page.getByText("ALMEIDA SERVICOS LTDA").first()).toBeVisible();

  await page.getByRole("button", { name: /GRUPO ALMEIDA OFICIAL/ }).first().click();
  await expect(page.getByRole("button", { name: /GRUPO ALMEIDA MARTINS/ }).first()).toBeVisible();
});
