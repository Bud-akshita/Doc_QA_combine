from docling.datamodel.base_models import InputFormat
# from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker
# from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
from docling.document_converter import DocumentConverter,PdfFormatOption
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import Document
from docling.chunking import HybridChunker
from transformers import AutoTokenizer
from docling.datamodel.pipeline_options import (
    AcceleratorOptions,
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)

prompt = ChatPromptTemplate.from_template(
    """
    Answer the questions based on the provided context only.
    Please provide the most accurate response based on the question
    <context>
    {context}
    </context>
    Questions:{input}
    """
)

file_path = "uploads/SBI_LOAN.pdf"
question = "intereset on term loan?"
in_question = "what is the "+question

embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
groq_api_key='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'
llm=ChatGroq(groq_api_key=groq_api_key,model_name="llama-3.1-8b-instant")

# Load a document
# pipeline_options = PdfPipelineOptions(
#     do_ocr=True,
#     ocr_options=EasyOcrOptions(lang=["en"])  # 👈 explicitly set language
# )

accelerator_options = AcceleratorOptions(
    num_threads=8,
    device="cpu",
    cuda_use_flash_attention2=False
)

pipeline_options = PdfPipelineOptions()
pipeline_options.accelerator_options = accelerator_options
pipeline_options.do_ocr = True
pipeline_options.do_table_structure = True
pipeline_options.table_structure_options.do_cell_matching = True

ocr_options = TesseractCliOcrOptions(force_full_page_ocr=True)
pipeline_options.ocr_options = ocr_options

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
        )
    }
)

# converter = DocumentConverter(format_options={
#     InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
# })
doc = converter.convert(file_path)
dl_doc = doc.document
# print(dl_doc)
if dl_doc:
    print("got data")
else : 
    print("did not get any data")

# Use HierarchicalChunker
# chunker = HierarchicalChunker(
#     levels=["section", "subsection", "paragraph"],  # hierarchy depth
#     max_tokens=500,   # optional safeguard to not exceed embedding limits
#     overlap=50        # overlap tokens between chunks for context
# )

# Use HybridChunker
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2", max_tokens= 150)
chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True, max_tokens=480)

chunks = list(chunker.chunk(dl_doc))
print(len(chunks))
# for chunk in chunks:
#     # Each chunk.meta.doc_items is a list of TextItem
#     for item in chunk.meta.doc_items:
#         for prov in item.prov:
#             if prov.page_no == 6:   # check for page 6
#                 print(chunk.text)
#                 print("-------------------------------------------")

docs = [Document(page_content=chunk.text, metadata={}) for chunk in chunks]
vectorstore = FAISS.from_documents(docs, embedding_model, distance_strategy="COSINE")

results = vectorstore.similarity_search_with_score(question, k=15)
print("length of result:", len(results))

filtered_docs = []
# score comes between 0 to 2 (0 means similar 1 means average 2 means opposite)
for i, (doc, score) in enumerate(results):
    if score <= 1.2 :
        print(f"\n--- Chunk {i+1} ---")
        print("score:", score)
        print("Content:", doc.page_content)
        print("Metadata:", doc.metadata)
        filtered_docs.append(doc)

final_prompt = prompt.format(context=filtered_docs, input=in_question)
response = llm.invoke(final_prompt)
result = response.content
print(result)
