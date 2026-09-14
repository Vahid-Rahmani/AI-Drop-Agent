# Training data

Future records should follow:

`INPUT STATE -> DECISION -> ACTION -> RESULT -> REVIEW`

Store source references and observed timestamps separately from model inferences. Exclude credentials, payment data, unnecessary customer PII, and unredacted support transcripts. Human corrections must be attributable and retained as review metadata, not silently merged into facts.
