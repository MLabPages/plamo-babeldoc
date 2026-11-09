"""参考文献の判定のテスト（実際の論文で BabelDOC が送った段落の形をもとにした例）。

  .venv\Scripts\python.exe tests\test_references.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paperapp.references import is_reference_entry  # noqa: E402

REFS = [
    # APA 1 項目
    "Gao, Y., Lee, D., Burtch, G., & Fazelpour, S. (2025). Take caution in using LLMs as human surrogates. "
    "Proceedings of the National Academy of Sciences, 122(24), https://doi.org/10.1073/pnas.2501660122",
    # 書式の目印つき
    "<style id='1'>Brucks, M., & Toubia, O. (2025).</style> Prompt architecture induces methodological artifacts.",
    # 途中で切れた断片
    "500: A data set for building digital twins of over 2,000 people. Marketing Science, 44(6), 1446–1455. "
    "https://doi.org/10.1287/mksc.2025.0262",
    # 参考文献欄がまとめて 1 段落（Elsevier 形式）
    " ".join([
        "Luangrath, A.W., Peck, J., Hedgcock, W., Xu, Y., 2022. Observing product touch: the vicarious haptic effect "
        "in digital marketing and virtual reality. J. Market. Res. 59 (2), 306–326. https://doi.org/10.1177/00222437211059540.",
        "Peck, J., Childers, T.L., 2003. Individual differences in haptic information processing. J. Consum. Res. 30 (3), "
        "430–442. https://doi.org/10.1086/378619.",
        "Krishna, A., Morrin, M., 2008. Does touch affect taste? J. Consum. Res. 34 (6), 807–818. https://doi.org/10.1086/523286.",
    ] * 2),
    # IEEE 形式（番号つき）
    "Pirita Ihamäki and Katriina Heljakka, “Robot Pets as Serious Toys,” Pori, Finland, August 2021. "
    "[2] Koh WQ, Ang FXH, Casey D, “Impacts of Low-cost Robotic Pets for Older Adults,” JMIR Rehabil Assist Technol, 2021. "
    "[3] Milyn C. Moy, “Gesture-Based Interaction with a Pet Robot,” AAAI, 1999. "
    "[4] Y. Kim, “Cute robots,” Proc. HRI, 2020, pp. 11–19." * 1,
]

BODY = [
    # 引用の多い本文段落
    "Shoppers place a high value on tactile input (Krishna et al., 2024), and retailers are well aware of the "
    "importance of product touch for consumers (Liu, W. et al., 2023a). Research has provided ample evidence of the "
    "role of haptic product cues in consumer responses (De Canio and Fuentes-Blasco, 2021; Kergoat et al., 2012; "
    "Krishna et al., 2024; Pantoja et al., 2020). " * 3,
    "Silicon samples consist of synthetically generated participants that seek to mimic human respondents to "
    "describe, explain and predict human behavior (Sarstedt et al., 2024).",
    "In 2023, worldwide retail e-commerce sales were estimated at $5.8 trillion (Statista, 2024).",
    "シリコンサンプルは、人間の回答者を模倣する合成的な参加者である（Sarstedt et al., 2024）。",
    "Figure 2. Input PWM vs corresponding motor angular speed (2024).",
]


def main() -> None:
    bad = [t[:70] for t in REFS if not is_reference_entry(t)] + [t[:70] for t in BODY if is_reference_entry(t)]
    for b in bad:
        print("NG:", b)
    print(f"{len(REFS) + len(BODY) - len(bad)}/{len(REFS) + len(BODY)} OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
