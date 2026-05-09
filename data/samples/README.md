# Dados de exemplo

Esta pasta contém arquivos CSV de exemplo prontos pro `FileBot` consumir.

**Como usar:**
```bash
# Copia um arquivo de exemplo pra pasta de drop e o bot vai pegá-lo na próxima execução
cp data/samples/readings_pcm_2026-05-08.csv data/drop/

# Ou, no Windows PowerShell:
Copy-Item .\data\samples\readings_pcm_2026-05-08.csv .\data\drop\
```

Após o processamento, o arquivo será movido para `data/archive/` com sufixo de timestamp.

**Arquivos:**

- `readings_pcm_2026-05-08.csv` — leituras em unidades SI (°C, V, A, kW)
- `readings_termografia_2026-05-09.csv` — só temperatura/vibração, em °F (testa conversão)
