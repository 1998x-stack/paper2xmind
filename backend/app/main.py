from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import papers, chat, categories

app = FastAPI(title="Paper Research Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(chat.router)
app.include_router(categories.router)


@app.get("/")
async def root():
    return {"message": "Paper Research Platform API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
