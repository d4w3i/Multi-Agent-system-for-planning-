# Test Implementation Logic

## Strategia

**Principi**:
- Isolation: ogni test usa una nuova istanza
- Fixtures reali: nessun mock, file Python parsati con tree-sitter
- Coverage: unit + edge cases + integration

**Struttura**:
- 14 test CallGraphBuilder (parsing, grafo, output)
- 15 test ContextGenerator (dipendenze, generazione file)
- 5 fixtures minimali

## Fixtures

### simple_functions.py
Catena: `helper_function ← process_data ← main_function`

Testa: parsing base, risoluzione chiamate dirette, relazioni calls/called_by, leaf/entry points.

### class_methods.py
Classe `DataProcessor` con metodi che chiamano `self.method()`.

Testa: full_name (`ClassName.method`), risoluzione self.method(), catene di chiamate tra metodi.

### recursive.py
`fibonacci()` e `factorial()` ricorsive.

Testa: funzione in calls/called_by di se stessa, nessun loop infinito in `get_all_dependencies()`.

### edge_cases.py
Funzioni vuote, built-in calls (`print`, `len`), import esterni, single-line.

Testa: built-in NON nel grafo, funzioni vuote sono leaf, parsing edge cases.

### empty_file.py
File senza funzioni.

Testa: nessun crash, call_graph vuoto.

## Test CallGraphBuilder

### Parsing Base
- **test_parse_simple_functions**: 3 funzioni estratte, chiamate risolte, relazioni bidirezionali
- **test_parse_class_methods**: full_name corretto, is_method=True, self.method() risolto
- **test_parse_recursive_function**: ricorsione rilevata (func in func.calls)

### Edge Cases
- **test_empty_file**: nessun crash, grafo vuoto
- **test_builtin_calls_not_tracked**: print/len/max NON nel grafo, is_leaf=True
- **test_empty_function** / **test_single_line_function**: parsing corretto

### Special Nodes
- **test_mark_leaf_functions**: is_leaf=True se calls=[]
- **test_mark_entry_points**: is_entry_point=True se called_by=[]

### Output
- **test_to_json**: struttura {functions, edges, stats}, stats corretti, JSON valido
- **test_to_mermaid**: sintassi Mermaid, stili :::entry e :::leaf, archi -->

### Integration
- **test_analyze_repository**: analizza directory, tutti file parsati, special nodes marcati
- **test_file_and_line_tracking**: file path e line number corretti
- **test_code_extraction**: campo code popolato con def e body

## Test ContextGenerator

### Dependency Collection
- **test_get_all_dependencies**: raccolta ricorsiva completa (main → process_data → helper)
- **test_get_dependencies_leaf_function**: leaf ritorna solo se stesso
- **test_get_dependencies_middle_function**: deps corrette, NON include callers
- **test_get_dependencies_nonexistent_function**: ritorna set vuoto

### Edge Cases
- **test_circular_dependency**: ricorsione gestita, nessun loop infinito, no duplicati
- **test_deep_dependency_chain**: catena lunga inclusa completamente

### Context Generation
- **test_generate_context_file**: file .txt creato, sezioni DEPENDENCIES/TARGET/USAGE
- **test_generate_context_file_without_callers**: flag include_callers=False funziona
- **test_generate_context_file_for_leaf**: leaf senza dipendenze genera file corretto
- **test_generate_context_file_nonexistent**: ritorna None, nessun file

### Metadata & Batch
- **test_generate_metadata_json**: file .json con struttura corretta
- **test_generate_all_context_files**: genera .txt e .json per tutte le funzioni
- **test_context_file_directory_creation**: crea directory nested automaticamente
- **test_context_content_quality**: contenuto ben formattato
- **test_no_duplicate_dependencies**: set garantisce unicità

## Running Tests

```bash
# Quick start
source .venv/bin/activate && pytest -v

# Singolo file
pytest tests/test_call_graph_builder.py -v

# Con coverage
pytest --cov=. --cov-report=html

# Stop al primo errore
pytest -x
```

## Note Implementative

**Niente mock**: Tree-sitter richiede bytes reali, fixtures minimali sono veloci (29 test in 0.03s).

**tmp_path**: Pytest fixture per directory temporanea, auto-cleanup, nessun file spazzatura.

**conftest.py**: Aggiunge project root a sys.path per import dei moduli.

**Print output**: CallGraphBuilder stampa durante parsing. Sopprimere con `pytest --quiet`.

## Possibili Estensioni

**Test mancanti**: invalid syntax, nested classes, decorators, async/await, type hints.
