from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import csv
import os
import urllib.parse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_script(script_name, *args):
    result = subprocess.run(["sh", script_name] + list(args), capture_output=True, text=True)
    return result.stdout.strip()


def get_affected_functions():
    subprocess.run(["python", "Backend/functionfind.py"], text=True)


def get_recipe_test():
    subprocess.run(["python", "Backend/Functiontotest.py"], capture_output=True, text=True)
    subprocess.run(["python", "Backend/Recipegenerator.py"], capture_output=True, text=True)
    subprocess.run(["python", "Backend/RecipeSegragator.py"], capture_output=True, text=True)

    testcases = set()
    recipes = set()
    output_csv = "Test/output_with_recipes.csv"

    if not os.path.exists(output_csv):
        return [], []

    with open(output_csv, "r", newline="") as csvfile:
        csvreader = csv.reader(csvfile)
        next(csvreader, None)  # Skip header row

        for row in csvreader:
            if len(row) >= 4:
                testcase, recipe = row[2].strip(), row[3].strip()
                if testcase:
                    testcases.add(testcase)
                if recipe:
                    recipes.add(recipe)

    return list(testcases), list(recipes)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/run", response_class=HTMLResponse)
def run(request: Request, branch_name: str = Form(...), number_of_commits: str = Form(...)):
    subprocess.run(["sh", "Backend/gitPartClone.sh", branch_name, number_of_commits], capture_output=True, text=True)
    subprocess.run(["sh", "Backend/gitFilesChanged.sh", number_of_commits], capture_output=True, text=True)

    get_affected_functions()
    subprocess.Popen(r".\PartRepo\HDMTOS\Validation\iVal\BuildScripts\BuildTPLFiles.bat", shell=True)

    testcases, recipes = get_recipe_test()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "testcases": testcases,
        "recipes": recipes
    })


@app.get("/get_agents")
def get_agents():
    result = subprocess.run(["sh", "get_agents.sh"], capture_output=True, text=True)
    tester = result.stdout.strip().split("\n")
    return {"tester": tester}


class TesterSelection(BaseModel):
    testers: list[str]


@app.post("/run_final")
def run_final_build(selection: TesterSelection):
    if not selection.testers:
        raise HTTPException(status_code=400, detail="No testers selected.")

    outputs = {}

    for tester in selection.testers:
        result = subprocess.run(["python", "run.py", tester], capture_output=True, text=True)
        outputs[tester] = result.stdout.strip()

    return {"message": "Final build started", "output": outputs}


@app.get("/send_email")
def send_email():
    result_link = "http://127.0.0.1:5000/view_results"
    subject = urllib.parse.quote("Build Results - Click to View")
    body = urllib.parse.quote(f"Hello,\n\nClick the link below to view the Build results:\n{result_link}")

    mailto_link = f"mailto:?subject={subject}&body={body}"

    return {"link": mailto_link}


@app.get("/view_results", response_class=HTMLResponse)
def view_results():
    csv_path = os.path.join("Result", "results.csv")

    if not os.path.exists(csv_path):
        return "<h2 style='color: red;'>No results found!</h2>"

    table_html = """
    <html>
    <head>
        <title>Build Results</title>
        <style>
            body { font-family: 'Arial', sans-serif; padding: 20px; background-color: #f9f9f9; }
            h2 { text-align: center; color: #0071C5; font-size: 24px; }
            .container { width: 100%; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; background: white; white-space: nowrap; }
            th, td { border: 1px solid #ddd; padding: 8px 15px; text-align: left; }
            th { background-color: #0071C5; color: white; font-size: 16px; }
            tr:nth-child(even) { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h2>Build Results</h2>
        <div class="container">
            <table>
    """

    with open(csv_path, "r", newline="") as csvfile:
        csvreader = csv.reader(csvfile)
        headers = next(csvreader, None)

        if headers:
            table_html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"

        for row in csvreader:
            table_html += "<tr>" + "".join(f"<td>{col}</td>" for col in row) + "</tr>"

    table_html += """
            </table>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=table_html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
