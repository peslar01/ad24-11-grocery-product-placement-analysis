# Optimising Product Placement Using Grocery Purchase Data

This project analyses the **Instacart Online Grocery Shopping Dataset (2017)** to understand purchasing patterns of grocery customers. The goal is to explore relationships between products that are frequently bought together and to use these insights to support product placement optimisation for grocery retail.

The final outcome is an interactive web dashboard that communicates purchasing behaviour and provides data-driven recommendations for product placement and category organisation.

**Key findings:** Across 3.4 million orders from ~206,000 customers, Produce and Dairy & Eggs emerge as the strongest co-purchased department pair (~1.8 million shared orders), pointing directly to adjacency opportunities on the shop floor. The overall reorder rate sits at 58%, with everyday staples such as bananas, milk, and water exceeding 80% — a clear signal for loyalty-driven assortment decisions. Order activity peaks on Sundays and Mondays between 09:00 and 15:00, with very little traffic outside 06:00–22:00.

## Project Organisation
The visualization product development is organised according to the following process model:

![The visualization product development process](docs/pics/vizproductprocess.png)

Code and configurations used in the different project phases are stored in the corresponding subfolders. Documentation artefacts in the form of a Quarto project are provided in `docs`.

| Phase | Code folders | Documentation section | `docs`-File |
|:-------|:---|:---|:---|
| Project Understanding | - | Project Charta | project_charta.qmd |
| Data Acquisition and Exploration | `data_acquisition`, `eda` | Data Report | data_report.qmd |
| Visual Encoding and Design | - | Visual Design Report | - (not submitted) |
| Evaluation | `evaluation` | Evaluation | - (not submitted) |
| Deployment | `deployment` | Deployment | - (not submitted) |

Raw and processed data files are stored in the `data/` folder.

See section `Quarto Setup and Usage` for instructions on how to build and serve the documentation website using Quarto.

The rendered documentation website (Project Charta, Data Report, and Dashboard) is hosted on GitHub Pages and can be accessed here:

[Project Repository and Documentation on GitHub](https://github.com/peslar01/ad24-11-grocery-product-placement-analysis.git)

## Python Environment Setup and Management with uv
Make sure to have uv installed: https://docs.astral.sh/uv/getting-started/installation/

After cloning the repository, create the python environment with all dependencies based on the `.python-version`, `pyproject.toml` and `uv.lock` files by running
```bash
uv sync
```

To add new dependencies, use
```bash
uv add <package>
```
which will add the package to `pyproject.toml` and update the `uv.lock` file. You can also specify a version, e.g. `uv add pandas==2.0.3`.

Remove packages with
```bash
uv remove <package>
```

Commit changes to `pyproject.toml` and `uv.lock` files into version control.

Run `uv sync` after pulling changes to update the local environment.

Whenever the python environment is used, make sure to prefix every command that uses python with `uv run`, e.g.
```bash
uv run python script.py
```

You can also run
```bash 
source .venv/bin/activate
```
to activate the project Python environment in a terminal session in order to avoid having to prefix every command.

## Running the Dashboard

The deployment is a Streamlit web application located in `deployment/app.py`. To run it locally:

```bash
uv run streamlit run deployment/app.py
```

Then open the URL shown in the terminal (usually `http://localhost:8501`) in your browser.

## Quarto Setup and Usage

### Setup Quarto

1. [Install Quarto](https://quarto.org/docs/get-started/)
2. Optional: [quarto-extension for VS Code](https://marketplace.visualstudio.com/items?itemName=quarto.quarto)
3. If working with svg files and pdf output you will need to install rsvg-convert:
    * On macOS: `brew install librsvg`
    * On Windows using chocolatey:
      * [Install chocolatey](https://chocolatey.org/install#individual)
      * [Install rsvg-convert](https://community.chocolatey.org/packages/rsvg-convert): `choco install rsvg-convert`

Source `*.qmd` and configuration files are in the `docs` folder. The Quarto project configuration is in `docs/_quarto.yml`.

With embedded python code chunks that perform computations, you need to make sure that the python environment is activated when rendering. This can be done by prefixing the render command with `uv run`, e.g.:
```bash
uv run quarto render
```

### Working on the Documentation

1. Make changes to the `.qmd` source files in the `docs` folder
2. Make sure the project Python environment is activated (see Python environment setup and management)
3. Preview locally: `quarto preview` from the `docs` folder
4. Build the documentation website: `uv run quarto render` from the `docs` folder. This renders to `docs/build`
5. Check the website locally by opening `docs/build/index.html` in a browser
