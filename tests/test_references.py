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
    # 引用の多い本文段落（テスト用に作った例文）
    "Readers often judge a book by its weight in the hand (Alder et al., 2021), and publishers know that paper "
    "texture shapes first impressions (Brook, R. et al., 2019a). Earlier studies link cover materials to "
    "perceived value (Cole and Dunmore-Hale, 2018; Ernst et al., 2016; Alder et al., 2021; Fenwick et al., 2020). " * 3,
    "Synthetic respondents are simulated people that imitate survey participants in order to "
    "anticipate how real groups would answer (Garner et al., 2022).",
    "In 2022, global spending on board games was estimated at $13.4 billion (Market Survey, 2023).",
    "合成回答者は、調査参加者を模倣するシミュレーション上の人物である（Garner et al., 2022）。",
    "Figure 3. Motor current versus wheel speed under load (2023).",
]


def main() -> None:
    bad = [t[:70] for t in REFS if not is_reference_entry(t)] + [t[:70] for t in BODY if is_reference_entry(t)]
    for b in bad:
        print("NG:", b)
    print(f"{len(REFS) + len(BODY) - len(bad)}/{len(REFS) + len(BODY)} OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
