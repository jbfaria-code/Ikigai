import { describe, expect, it } from "vitest";
import { findDenylisted } from "@/lib/locale/denylist";

describe("findDenylisted", () => {
  it.each([
    ["Vou baixar o arquivo no celular.", ["celular", "baixar", "arquivo"]],
    ["O meu time ganhou.", ["time"]],
    ["Apanhei o ÔNIBUS.", ["ônibus"]],
    ["O utilizador quer registrar-se.", ["registrar"]],
  ])("flags Brazilian markers in pt-PT: %s", (text, expected) => {
    expect(findDenylisted(text, "pt-PT").sort()).toEqual([...expected].sort());
  });

  it.each([
    "Vou transferir o ficheiro no telemóvel.",
    "A minha equipa ganhou; o ecrã é grande.",
    "Temos tempo; é uma telenovela.", // 'tela' / 'time' only as whole words
    "O utilizador quer registar-se.",
  ])("accepts European Portuguese: %s", (text) => {
    expect(findDenylisted(text, "pt-PT")).toEqual([]);
  });

  it("flags British spellings in en-US", () => {
    expect(findDenylisted("My favourite colour; love, Mum", "en-US").sort()).toEqual(
      ["Mum", "colour", "favourite"].sort(),
    );
  });

  it("accepts American English and does not match inside words", () => {
    expect(findDenylisted("My favorite color, Mom. Mumbai is in the center.", "en-US")).toEqual([]);
  });
});
