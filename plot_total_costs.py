import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from typing import overload

def plotting(rows, outPath= "dso_scheme_total_cost_comparison.png"):
    plot_data = sorted(rows, key=lambda x: (-x["total"]))

    labels = [f"{item['DSO']} — Scheme {item['Scheme']}" for item in plot_data]
    components = {
        "base price": [item["base price"] for item in plot_data],
        "power tariff": [item["power tariff"] for item in plot_data],
        "reactive power fee": [item["reactive power fee"] for item in plot_data],
        "energy fee": [item["energy fee"] for item in plot_data],
    }

    plt.style.use("seaborn-v0_8")
    fig, ax = plt.subplots(figsize=(18, 10))

    x = range(len(labels))
    component_colors = {
        "base price": "#9ecae1",
        "power tariff": "#4f81bd",
        "reactive power fee": "#b6d7a8",
        "energy fee": "#c7b8ea",
    }

    bottom = [0] * len(labels)
    for component_name in ["base price", "power tariff", "reactive power fee", "energy fee"]:
        values = components[component_name]
        ax.bar(
            x,
            values,
            bottom=bottom,
            label=component_name,
            color=component_colors[component_name],
            edgecolor="black",
            linewidth=0.2,
            width=0.8,
        )
        bottom = [bottom[i] + values[i] for i in range(len(values))]

    ax.set_title("Annual DSO tariff cost composition by scheme", fontsize=15, weight="bold")
    ax.set_xlabel("DSO scheme")
    ax.set_ylabel("Annual cost (€)")
    ax.grid(axis="y", linestyle="--", alpha=0.45)
    ax.tick_params(axis="x", labelrotation=90)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7)
    ax.margins(y=0.05)

    fig.tight_layout()
    fig.savefig(outPath, dpi=300, bbox_inches="tight")
    print("Saved stacked component-cost figure to dso_scheme_total_cost_comparison.png")

class plot():
    @overload
    def __init__(self, data_source: str, outPath: str) -> None: ...

    # 2. Second signature for the type checker
    @overload
    def __init__(self, data_source: list[dict], outPath: str) -> None: ...

    # 3. The ACTUAL runtime implementation (no decorator)
    def __init__(self, data_source: str | list[dict], outPath: str) -> None:
        rows = []
        
        # Check the type at runtime to decide what to do
        if isinstance(data_source, str):
            with open(data_source, newline="", encoding="latin-1") as input_file:
                reader = csv.DictReader(input_file)
                data_source = list(reader)
        else:
            for record in data_source:
                try:
                    row = {
                        "DSO": record.get("DSO", ""),
                        "Scheme": int(float(record.get("Scheme", "0"))),
                        "base price": float(record.get("base price", 0) or 0),
                        "power tariff": float(record.get("power tariff", 0) or 0),
                        "reactive power fee": float(record.get("reactive power fee", 0) or 0),
                        "energy fee": float(record.get("energy fee", 0) or 0),
                        "total": float(record.get("total", 0) or 0),
                    }
                    rows.append(row)
                except (TypeError, ValueError):
                    continue
        
            plotting(rows, outPath)
            pass

def main():
    rows = []
    with open("results.csv", newline="", encoding="latin-1") as input_file:
        reader = csv.DictReader(input_file)
        for record in reader:
            try:
                row = {
                    "DSO": record.get("DSO", ""),
                    "Scheme": int(float(record.get("Scheme", "0"))),
                    "base price": float(record.get("base price", 0) or 0),
                    "power tariff": float(record.get("power tariff", 0) or 0),
                    "reactive power fee": float(record.get("reactive power fee", 0) or 0),
                    "energy fee": float(record.get("energy fee", 0) or 0),
                    "total": float(record.get("total", 0) or 0),
                }
                rows.append(row)
            except (TypeError, ValueError):
                continue

    plotting(rows)


if __name__ == '__main__':
    main()
