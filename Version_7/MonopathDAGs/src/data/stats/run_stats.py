import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
class StatCSV:
    def __init__(self, path: str):
        self.df = pd.read_csv(path)
        self.results = []

    def ttest(self, outcome: str, group: str, paired: bool = False, id_cols: list[str] = None, alpha: float = 0.05):
        if paired:
            if not id_cols:
                raise ValueError("Paired t-test requires id_cols")

            # Drop NAs and filter for complete (graph_id, username) pairs
            df = self.df.dropna(subset=[outcome, group] + id_cols)
            key = id_cols

            gcounts = (
                df.groupby(key + [group])
                .size()
                .unstack(fill_value=0)
            )

            valid_keys = gcounts[(gcounts[True] == 1) & (gcounts[False] == 1)].index
            df_filtered = df.set_index(key).loc[valid_keys].reset_index()

            x = df_filtered[df_filtered[group] == True].set_index(key)[outcome]
            y = df_filtered[df_filtered[group] == False].set_index(key)[outcome]
            x, y = x.align(y, join="inner")

            diff = x - y
            stat, p = stats.ttest_rel(x, y)
            cohens_d = diff.mean() / diff.std(ddof=1)
            ci = stats.t.interval(0.95, len(diff)-1, loc=diff.mean(), scale=stats.sem(diff))
        else:
            df = self.df.dropna(subset=[outcome, group])
            x = df[df[group] == True][outcome]
            y = df[df[group] == False][outcome]

            stat, p = stats.ttest_ind(x, y)
            nx, ny = len(x), len(y)
            s_pooled = (((nx - 1) * x.std(ddof=1) ** 2 + (ny - 1) * y.std(ddof=1) ** 2) / (nx + ny - 2)) ** 0.5
            cohens_d = (x.mean() - y.mean()) / s_pooled
            ci = stats.t.interval(
                0.95,
                nx + ny - 2,
                loc=(x.mean() - y.mean()),
                scale=stats.sem(x - y if nx == ny else pd.concat([x, -y]))
            )

        result = {
            "test": "paired t-test" if paired else "independent t-test",
            "outcome": outcome,
            "group_1": True,
            "group_2": False,
            "mean_1": x.mean(),
            "mean_2": y.mean(),
            "std_1": x.std(ddof=1),
            "std_2": y.std(ddof=1),
            "n_1": len(x),
            "n_2": len(y),
            "stat": stat,
            "p_value": p,
            "significant": p < alpha,
            "cohens_d": cohens_d,
            "ci_lower": ci[0],
            "ci_upper": ci[1]
        }

        self.results.append(result)
        return result

    def to_dataframe(self):
        return pd.DataFrame(self.results)

    def to_latex(self, caption="Statistical Results", label="tab:results"):
        df = self.to_dataframe()
        
        if df.empty:
            return "% No results"
        return df.to_latex(
            index=False,
            float_format="{:.3f}".format,
            caption=caption,
            label=label,
            longtable=False
        )
    import matplotlib.pyplot as plt

    def plot_likert(
        self,
        outcome_cols: list[str],
        group_col: str,
        likert_range=range(1, 6),
        title="Likert Ratings by Group",
        colors: list[str] = None
    ):
        """
        Plot stacked Likert bar charts comparing multiple outcomes by group.

        Args:
            outcome_cols (list[str]): Columns representing Likert responses.
            group_col (str): Column used to group responses (e.g., control vs. sample).
            likert_range (range): Likert scale range. Default is range(1, 6).
            title (str): Title of the plot.
            colors (list[str]): List of colors corresponding to each Likert level.
        """
        if colors is None:
            colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60"]

        df = self.df.copy()

        # Force consistent group order
        groups = sorted(df[group_col].unique())
        print(f"🔍 Sanity check — group order: {groups}")

        # Optional: map known group labels
        group_label_map = {True: "Control", False: "Sample"}
        group_labels = [group_label_map.get(g, str(g)) for g in groups]

        # Prepare percentage data for each question
        data = {}
        for col in outcome_cols:
            grp = df.groupby(group_col)[col].value_counts(normalize=True).unstack().fillna(0)
            grp = grp.reindex(columns=sorted(likert_range), fill_value=0) * 100
            data[col] = grp

        n_questions = len(outcome_cols)
        n_groups = len(groups)
        bar_width = 0.35
        index = list(range(n_questions))

        fig, ax = plt.subplots(figsize=(1.5 * n_questions * n_groups, 6))
        bottoms = {g: [0] * n_questions for g in groups}

        for i, level in enumerate(sorted(likert_range)):
            for j, g in enumerate(groups):
                heights = [data[q].loc[g, level] if level in data[q].columns else 0 for q in outcome_cols]
                pos = [ix + j * bar_width for ix in index]
                ax.bar(
                    pos,
                    heights,
                    bar_width,
                    bottom=bottoms[g],
                    label=str(level) if j == 0 else "",
                    color=colors[i],
                    edgecolor="white"
                )
                for k, h in enumerate(heights):
                    if h >= 5:
                        ax.text(
                            pos[k],
                            bottoms[g][k] + h / 2,
                            f"{int(h)}%",
                            ha="center",
                            va="center",
                            fontsize=9
                        )
                bottoms[g] = [bottoms[g][k] + heights[k] for k in range(n_questions)]

        # X-axis setup
        ax.set_xticks([ix + bar_width / 2 for ix in index])
        ax.set_xticklabels(outcome_cols, fontsize=12)
        ax.set_ylabel("Percent", fontsize=12)
        ax.set_title(title, fontsize=14, pad=10)
        ax.set_ylim(0, 100)
        ax.spines["top"].set_visible(False)

        # Add group labels beneath each pair of bars
        for j, _ in enumerate(groups):
            for i in range(n_questions):
                xpos = index[i] + j * bar_width
                ax.text(
                    xpos,
                    -7,
                    group_labels[j],
                    ha="center",
                    va="top",
                    fontsize=10
                )

        ax.legend(title="Likert Value", loc="upper left", bbox_to_anchor=(1.01, 1))
        plt.tight_layout()
        plt.show()




# s = StatCSV("/Users/aaronfanous/Downloads/evaluation_dump.csv")
# s.ttest("Q1", group="is_control", paired=True, id_cols=["graph_id", "username"])
# print(s.to_dataframe())
path = " "
s = StatCSV(path)
s.plot_likert(outcome_cols=["Q1", "Q2", "Q3", "Q4", "Q5"], group_col="is_control")
for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
    s.ttest(
        outcome=q,
        group="is_control",
        paired=True,
        id_cols=["graph_id", "username"]
    )

# Print LaTeX table
print(s.to_latex(
    caption="Paired t-tests comparing control vs. sample responses",
    label="tab:likert_results"
))