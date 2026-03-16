# Optimising Product Placement Using Grocery Purchase Data

## Project Description

This project analyses the **Instacart Online Grocery Shopping Dataset (2017)** to understand purchasing patterns of grocery customers.

The goal of the project is to explore relationships between products that are frequently bought together and to use these insights to support store layout optimisation for a new supermarket.

By analysing the dataset, we aim to answer questions such as:

- Which products are most frequently purchased?
- Which products are commonly bought together?
- Are there typical purchasing patterns across different product categories?
- How can these patterns be used to optimise product placement in a physical store?

The final outcome of the project is a data visualisation product that communicates these insights and provides recommendations for optimal product placement and category organisation in a grocery store.

## Dataset

This project uses the **Instacart Online Grocery Shopping Dataset (2017)** which contains anonymised grocery orders from over 200,000 users.

The dataset includes:

- orders
- products
- product categories
- order history of users
- reordered products

This allows the analysis of:
- product popularity
- purchasing behaviour
- product associations (products bought together)

## Project Organisation
The visualization product development is organised according to the following process model:

![The visualization product development process](docs/pics/vizproductprocess.png)

Code and configurations used in the different project phases are stored in the correspoding subfolders. Documentation artefacts in the form of a Quarto project are provided in `docs`.

| Phase | Code folders | Documentation section | `docs`-File |
|:-------|:---|:---|:---|
| Project Understanding | -  | Project Charta | project_charta.qmd  |
| Data Acquisition and Exploration | `eda` | Data Report | data_report.qmd  |
| Visual Encoding and Design | `encoding-design`  | Visual Encoding and Design | viz_encoding_design.qmd  |
| Evaluation | `evaluation`  | Evaluation | evaluation.qmd  |
| Deployment | `deployment` | Deployment | deplyoment.qmd |


The project follows the data visualisation product development process used in the course and is structured into the following phases:

1. **Project Understanding**
   - Define the project goal and research questions
   - Understand the Instacart dataset and its structure

2. **Data Acquisition and Exploration**
   - Load and explore the Instacart dataset
   - Perform exploratory data analysis (EDA)
   - Identify purchasing patterns and frequently co-purchased products

3. **Visual Encoding and Design**
   - Design visualisations to communicate purchasing behaviour
   - Explore visual representations such as:
     - product frequency charts
     - product association networks
     - category-level purchasing patterns

4. **Evaluation**
   - Evaluate the clarity and effectiveness of the visualisations
   - Improve the design based on feedback

5. **Deployment**
   - Publish the final visualisation and documentation

## Documentation

The full project documentation and visualisations can be accessed here:

[Instacart Online Grocery Shopping Dataset](https://<your-github-username>.github.io/<repo-name>/)


See section `Quarto Setup and Usage` for instructions on how to build and serve the documentation website using Quarto.

## Python Environment Setup and Management with uv
Make sure to have uv installed: https://docs.astral.sh/uv/getting-started/installation/

After cloning the repository,  create the python environment with all dependencies based on the `.python-version`, `pyproject.toml` and `uv.lock` files by running
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

## Runtime Configuration with Environment Variables
The environment variables are specified in a .env-File, which is never commited into version control, as it may contain secrets. The repo just contains the file `.env.template` to demonstrate how environment variables are specified.

You have to create a local copy of `.env.template` in the project root folder and the easiest is to just rename it to `.env`.

The content of the .env-file is then read by the pypi-dependency: `python-dotenv`. Usage:
```python
import os
from dotenv import load_dotenv
```

`load_dotenv` reads the .env-file and sets the environment variables:

```python
load_dotenv()
```

which can then be accessed (assuming the file contains a line `SAMPLE_VAR=<some value>`):

```python
os.environ['SAMPLE_VAR']
```

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

### Deployment of the Documentation to GitHub Pages

The documentation website is deployed to GitHub Pages via a GitHub Actions workflow (`.github/workflows/publish.yml`). Every push to `main` triggers the workflow, which renders the Quarto project and deploys the result.

The setting `execute: freeze: auto` in `_quarto.yml` ensures that Python computations are only executed locally. Results are cached in `docs/_freeze` and checked into the repository, so the GitHub Actions runner does not need Python — it uses the pre-computed results.

#### Initial Setup (once)

1. In the GitHub repository settings, go to **Settings > Pages** and set the source to **GitHub Actions**
2. Render locally so that `_freeze` contains cached computation results:
   ```bash
   cd docs && uv run quarto render
   ```
3. Push the changes to `main`

The `_freeze` directory and the workflow file `.github/workflows/publish.yml` should already be tracked in the repository.


#### Publishing Updates

1. Build the website locally: `uv run quarto render` from the `docs` folder. This updates `docs/build` (gitignored) and `docs/_freeze` (checked in)
2. Check the website locally by opening `docs/build/index.html`
3. Commit and push all updated files (including `docs/_freeze`) to `main`. The GitHub Actions workflow will render and deploy the site automatically
