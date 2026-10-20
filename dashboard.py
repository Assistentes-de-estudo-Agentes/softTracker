#!/usr/bin/env python3
"""Dashboard local do SDDTrack. Execute: python dashboard.py"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import socket
import webbrowser
from pathlib import Path
import json, subprocess, os, urllib.parse, re
from sddtrack.stack_detector import detectar_stack

ROOT = Path(__file__).resolve().parent
DASH = ROOT / 'dashboard'
STATUS = ROOT / 'estado' / 'status.json'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASH), **kwargs)
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/api/status', '/api/refresh'):
            # Sempre reprocessa as especificações e o código atuais. Isso evita exibir
            # status.json antigo quando o ZIP foi extraído sobre uma pasta já usada.
            try:
                proc = subprocess.run(
                    [os.sys.executable, str(ROOT/'harness.py'), 'status', '--resumo'],
                    cwd=ROOT, capture_output=True, text=True, timeout=30
                )
                if proc.returncode != 0:
                    detalhe = (proc.stderr or proc.stdout or 'Erro sem detalhes').strip()
                    self.send_json({'error': f'Falha ao atualizar o estado do harness: {detalhe}'}, 500)
                    return
            except Exception as e:
                self.send_json({'error': f'Não foi possível sincronizar o harness: {e}'}, 500)
                return
            data = self.read_status()
            data['diagnostico'] = {
                'diretorio_dashboard': str(ROOT),
                'especificacoes': self.spec_paths(),
                'projeto': self.project_path(),
                'porta': self.server.server_port,
            }
            self.send_json(data); return
        if path == '/': self.path = '/index.html'
        return super().do_GET()
    def send_json(self, data, code=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def spec_paths(self):
        try:
            config = json.loads((ROOT / 'harness.json').read_text(encoding='utf-8'))
            paths = config.get('specs') or ['spec/spec.yaml']
            return [str((ROOT / p).resolve()) if not Path(p).is_absolute() else str(Path(p)) for p in paths]
        except Exception:
            return [str((ROOT / 'spec/spec.yaml').resolve())]
    def project_path(self):
        try:
            config = json.loads((ROOT / 'harness.json').read_text(encoding='utf-8'))
            p = Path(config.get('projeto', 'projeto'))
            return str((ROOT / p).resolve() if not p.is_absolute() else p)
        except Exception:
            return str((ROOT / 'projeto').resolve())
    def read_status(self):
        if STATUS.exists():
            try:
                data = json.loads(STATUS.read_text(encoding='utf-8'))
                # Use a mesma lista de manifestos configurada no harness.py.
                # O motor já aceita múltiplos arquivos; o dashboard também deve consolidá-los.
                try:
                    config = json.loads((ROOT / 'harness.json').read_text(encoding='utf-8'))
                except Exception:
                    config = {}
                manifestos = config.get('specs') or ['spec/spec.yaml']
                casos_de_uso = []
                stack_dict = {}
                stack_lista = []
                for manifesto in manifestos:
                    caminho = Path(manifesto)
                    if not caminho.is_absolute():
                        caminho = ROOT / caminho
                    try:
                        texto = caminho.read_text(encoding='utf-8')
                        if caminho.suffix.lower() == '.json':
                            spec_atual = json.loads(texto)
                        else:
                            import yaml
                            spec_atual = yaml.safe_load(texto) or {}
                        casos_de_uso.extend(spec_atual.get('casos_de_uso') or [])
                        stack_atual = spec_atual.get('stack')
                        if isinstance(stack_atual, dict):
                            stack_dict.update(stack_atual)
                        elif isinstance(stack_atual, list):
                            stack_lista.extend(stack_atual)
                    except Exception:
                        # A validação detalhada dos manifestos continua sendo feita pelo harness.
                        continue
                data['casos_de_uso'] = casos_de_uso

                # Detecta a stack a partir dos arquivos do projeto monitorado.
                # As declarações manuais complementam a detecção quando não há evidência no código.
                projeto_cfg = config.get('projeto', 'projeto')
                raiz_projeto = Path(projeto_cfg)
                if not raiz_projeto.is_absolute():
                    raiz_projeto = ROOT / raiz_projeto
                detectada = detectar_stack(raiz_projeto)

                declarada = stack_dict or stack_lista or config.get('stack', [])
                if isinstance(declarada, dict):
                    declarada_normalizada = [
                        {'nome': str(nome).replace('_', ' ').replace('-', ' ').title(),
                         'tecnologia': str(valor), 'origem': 'spec/configuração',
                         'confianca': 'Declarada', 'modo': 'declarada'}
                        for nome, valor in declarada.items() if valor not in (None, '', [])
                    ]
                elif isinstance(declarada, list):
                    declarada_normalizada = [
                        ({'nome': str(item.get('nome', item.get('categoria', 'Tecnologia'))),
                          'tecnologia': str(item.get('tecnologia', item.get('valor', ''))),
                          'origem': 'spec/configuração', 'confianca': 'Declarada', 'modo': 'declarada'}
                         if isinstance(item, dict) else
                         {'nome': 'Tecnologia', 'tecnologia': str(item), 'origem': 'spec/configuração',
                          'confianca': 'Declarada', 'modo': 'declarada'})
                        for item in declarada if item not in (None, '')
                    ]
                else:
                    declarada_normalizada = []

                # Evita duplicar uma tecnologia que já tenha sido identificada pelos arquivos.
                detectados_norm = [re.sub(r'[^a-z0-9]+', '', x['tecnologia'].lower()) for x in detectada]
                for item in declarada_normalizada:
                    norm = re.sub(r'[^a-z0-9]+', '', item['tecnologia'].lower())
                    if norm and not any(norm == d or (d and d in norm) for d in detectados_norm):
                        detectada.append(item)
                data['stack'] = detectada
                data['stack_raiz'] = str(raiz_projeto)
                data['stack_detectada_automaticamente'] = any(x.get('modo') != 'declarada' for x in detectada)
                return data
            except Exception as e: return {'error': f'Não foi possível ler status.json: {e}'}
        return {'error':'Estado ainda não gerado. Execute python harness.py init --projeto projeto --spec spec/spec.yaml.'}
    def log_message(self, fmt, *args): print('[dashboard] ' + fmt % args)

if __name__ == '__main__':
    host = '127.0.0.1'
    server = None
    last_error = None
    # Se já houver uma versão antiga do dashboard na porta 8765, inicia na próxima
    # porta livre. Assim o usuário não continua sem perceber vendo o processo antigo.
    for port in range(8765, 8786):
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError as e:
            last_error = e
    if server is None:
        raise SystemExit(f'Não foi possível encontrar uma porta livre entre 8765 e 8785: {last_error}')
    print('SDDTrack Dashboard iniciado.', flush=True)
    print(f'Pasta desta execução: {ROOT}', flush=True)
    print('Especificações: as listadas em harness.json.', flush=True)
    print(f'Abra exatamente este endereço: http://{host}:{server.server_port}', flush=True)
    if server.server_port != 8765:
        print(f'A porta 8765 já está em uso; esta execução foi iniciada na porta {server.server_port}.', flush=True)
    print('Use Ctrl+C para encerrar. O painel roda somente neste computador.', flush=True)
    webbrowser.open(f'http://{host}:{server.server_port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Dashboard encerrado.', flush=True)
    finally:
        server.server_close()
