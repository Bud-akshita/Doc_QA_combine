"""
    Answer the questions based on the provided context only.
    Please provide the most accurate response based on the context and questions.
    return a title paragraph combining the answer of the questions. if you are not able to find out answer of any question return not able to find information about this question.
    <context>
    {context}
    <context>

    title : {title}
    Questions:{input}
"""

for section in loan_config["loan"].values():
    title = section["title"]
    questions = ", ".join(section["questions"])

prompt.format(context=context, title =title, input=question)
