"""Detecção heurística da stack do projeto monitorado, sem instalar dependências extras.

A detecção é baseada em arquivos de configuração e código. É uma indicação útil,
mas não substitui validar a arquitetura real do projeto.
"""
from pathlib import Path
import json
import os
import re

IGNORAR_DIRS = {
    '.git', '.idea', '.vscode', '.venv', 'venv', '__pycache__', 'node_modules',
    'target', 'build', 'dist', '.next', 'coverage', 'vendor', 'bin', 'obj',
    '.gradle', '.pytest_cache', 'site-packages'
}
MAX_ARQUIVOS = 6000
MAX_TEXTO = 1_000_000


def _ler(path):
    try:
        if path.stat().st_size > MAX_TEXTO:
            return ''
        return path.read_text(encoding='utf-8', errors='ignore')
    except (OSError, ValueError):
        return ''


def detectar_stack(raiz):
    """Retorna tecnologias com evidência, confiança e origem da detecção."""
    raiz = Path(raiz)
    if not raiz.exists() or not raiz.is_dir():
        return []

    paths = []
    for current, dirs, files in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if d not in IGNORAR_DIRS and not d.startswith('.'))
        for filename in sorted(files):
            paths.append(Path(current) / filename)
            if len(paths) >= MAX_ARQUIVOS:
                break
        if len(paths) >= MAX_ARQUIVOS:
            break

    by_name = {}
    extensions = {}
    for p in paths:
        by_name.setdefault(p.name.lower(), []).append(p)
        extensions[p.suffix.lower()] = extensions.get(p.suffix.lower(), 0) + 1

    results = []
    seen = set()

    def add(category, tech, source, confidence='Alta'):
        key = re.sub(r'[^a-z0-9]+', '', tech.lower())
        if not key or key in seen:
            return
        seen.add(key)
        results.append({
            'nome': category,
            'tecnologia': tech,
            'origem': source,
            'confianca': confidence,
            'modo': 'detectada'
        })

    def texts(name):
        return [(p, _ler(p)) for p in by_name.get(name.lower(), [])]

    def has_any(name, patterns):
        return any(re.search(pattern, txt, re.I) for _, txt in texts(name) for pattern in patterns)

    def all_named_content(names):
        parts = []
        for name in names:
            for path, content in texts(name):
                parts.append((path, content))
        return parts

    # Java / JVM, Spring e ferramentas do build.
    java_files = [p for p in paths if p.suffix.lower() == '.java']
    kotlin_files = [p for p in paths if p.suffix.lower() == '.kt']
    if java_files:
        add('Linguagem', 'Java', java_files[0].name, 'Alta')
    elif kotlin_files:
        add('Linguagem', 'Kotlin', kotlin_files[0].name, 'Alta')
    elif 'pom.xml' in by_name:
        add('Linguagem', 'Java', 'pom.xml', 'Média')
    elif has_any('build.gradle', [r"id\s*\(?['\"]java['\"]", r'java-library']) or has_any('build.gradle.kts', [r"id\s*\(\s*['\"]java['\"]", r'java-library']):
        add('Linguagem', 'Java', 'arquivo de build Gradle', 'Média')
    if has_any('pom.xml', [r'<artifactId>spring-boot-starter(?:-[^<]+)?</artifactId>', r'<groupId>org\.springframework\.boot</groupId>']) or has_any('build.gradle', [r'org\.springframework\.boot', r'spring-boot-starter']) or has_any('build.gradle.kts', [r'org\.springframework\.boot', r'spring-boot-starter']):
        source = next((p.name for name in ('pom.xml', 'build.gradle', 'build.gradle.kts') for p, txt in texts(name) if re.search(r'springframework\.boot|spring-boot-starter', txt, re.I)), 'configuração JVM')
        add('Backend', 'Spring Boot', source, 'Alta')
    if 'pom.xml' in by_name:
        add('Build', 'Maven', 'pom.xml', 'Alta')
    if 'build.gradle' in by_name or 'build.gradle.kts' in by_name:
        p = 'build.gradle.kts' if 'build.gradle.kts' in by_name else 'build.gradle'
        add('Build', 'Gradle', p, 'Alta')

    # Web básico: HTML e CSS podem ser a stack de frontend mesmo sem framework.
    html_files = [p for p in paths if p.suffix.lower() in {'.html', '.htm'}]
    css_files = [p for p in paths if p.suffix.lower() == '.css']
    if html_files:
        add('Frontend', 'HTML', html_files[0].name, 'Alta')
    if css_files:
        add('Estilos', 'CSS', css_files[0].name, 'Alta')

    # JavaScript / TypeScript e frameworks usuais.
    package_jsons = texts('package.json')
    package_data = {}
    for p, content in package_jsons:
        try:
            parsed = json.loads(content)
            package_data.update(parsed.get('dependencies') or {})
            package_data.update(parsed.get('devDependencies') or {})
        except (json.JSONDecodeError, TypeError):
            pass
    if package_jsons or extensions.get('.js') or extensions.get('.jsx'):
        add('Runtime', 'Node.js', package_jsons[0][0].name if package_jsons else 'arquivos JavaScript', 'Alta' if package_jsons else 'Média')
    if extensions.get('.ts') or extensions.get('.tsx') or 'typescript' in package_data:
        source = package_jsons[0][0].name if package_jsons and 'typescript' in package_data else 'arquivos .ts/.tsx'
        add('Linguagem', 'TypeScript', source, 'Alta')
    elif extensions.get('.js') or extensions.get('.jsx') or package_jsons:
        add('Linguagem', 'JavaScript', package_jsons[0][0].name if package_jsons else 'arquivos .js/.jsx', 'Alta' if package_jsons else 'Média')
    for dep, tech, category in [
        ('@angular/core', 'Angular', 'Frontend'), ('react', 'React', 'Frontend'),
        ('next', 'Next.js', 'Frontend'), ('vue', 'Vue.js', 'Frontend'),
        ('vite', 'Vite', 'Build'), ('express', 'Express', 'Backend'),
        ('@nestjs/core', 'NestJS', 'Backend'), ('tailwindcss', 'Tailwind CSS', 'CSS/UI'),
        ('svelte', 'Svelte', 'Frontend'), ('nuxt', 'Nuxt', 'Frontend'),
    ]:
        if dep in package_data:
            add(category, tech, 'package.json', 'Alta')

    # Python e frameworks.
    py_files = [p for p in paths if p.suffix.lower() == '.py']
    py_manifests = all_named_content(['requirements.txt', 'pyproject.toml', 'Pipfile', 'setup.py'])
    if py_files or py_manifests:
        src = py_manifests[0][0].name if py_manifests else py_files[0].name
        add('Linguagem', 'Python', src, 'Alta')
    py_text = '\n'.join(txt for _, txt in py_manifests).lower()
    for pattern, tech in [(r'\bfastapi\b', 'FastAPI'), (r'\bdjango\b', 'Django'), (r'\bflask\b', 'Flask'), (r'\bstreamlit\b', 'Streamlit'), (r'\bpytest\b', 'pytest'), (r'\bsqlalchemy\b', 'SQLAlchemy')]:
        if re.search(pattern, py_text):
            add('Backend' if tech in {'FastAPI', 'Django', 'Flask'} else 'Ferramenta', tech, py_manifests[0][0].name if py_manifests else 'dependências Python', 'Alta')

    # PHP e frameworks.
    php_files = [p for p in paths if p.suffix.lower() == '.php']
    composer = texts('composer.json')
    composer_text = '\n'.join(txt for _, txt in composer).lower()
    if php_files or composer:
        add('Linguagem', 'PHP', composer[0][0].name if composer else php_files[0].name, 'Alta')
    if 'laravel/framework' in composer_text:
        add('Backend', 'Laravel', 'composer.json', 'Alta')

    # .NET / C#.
    csproj = [(p, _ler(p)) for p in paths if p.suffix.lower() == '.csproj']
    cs_files = [p for p in paths if p.suffix.lower() == '.cs']
    if csproj or cs_files:
        add('Linguagem', 'C#', csproj[0][0].name if csproj else cs_files[0].name, 'Alta')
    if any('Microsoft.NET.Sdk.Web' in txt or 'Microsoft.AspNetCore' in txt for _, txt in csproj):
        add('Backend', 'ASP.NET Core', csproj[0][0].name, 'Alta')

    # Go, Rust, Ruby.
    if 'go.mod' in by_name:
        add('Linguagem', 'Go', 'go.mod', 'Alta')
        go_text = '\n'.join(txt for _, txt in texts('go.mod')).lower()
        if 'github.com/gin-gonic/gin' in go_text: add('Backend', 'Gin', 'go.mod', 'Alta')
        if 'github.com/labstack/echo' in go_text: add('Backend', 'Echo', 'go.mod', 'Alta')
    cargo = texts('cargo.toml')
    if cargo:
        add('Linguagem', 'Rust', cargo[0][0].name, 'Alta')
        cargo_text = '\n'.join(txt for _, txt in cargo).lower()
        if re.search(r'\baxum\s*=', cargo_text): add('Backend', 'Axum', cargo[0][0].name, 'Alta')
        if re.search(r'\bactix-web\s*=', cargo_text): add('Backend', 'Actix Web', cargo[0][0].name, 'Alta')
    gemfile = texts('gemfile')
    if gemfile:
        add('Runtime', 'Ruby', gemfile[0][0].name, 'Alta')
        gem_text = '\n'.join(txt for _, txt in gemfile).lower()
        if re.search(r"gem\s+['\"]rails['\"]", gem_text): add('Backend', 'Ruby on Rails', gemfile[0][0].name, 'Alta')

    # Marcas de tecnologias de persistência encontradas nos arquivos de configuração.
    config_names = ['application.properties', 'application.yml', 'application.yaml', '.env', 'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
    config_texts = all_named_content(config_names)
    config_blob = '\n'.join(txt for _, txt in config_texts).lower()
    for pattern, tech in [
        (r'jdbc:postgresql:|image:\s*postgres(?:[:\s]|$)|postgresql://', 'PostgreSQL'),
        (r'jdbc:mysql:|image:\s*mysql(?:[:\s]|$)|mysql://', 'MySQL'),
        (r'mongodb(?:\+srv)?://|image:\s*mongo(?:[:\s]|$)', 'MongoDB'),
        (r'image:\s*redis(?:[:\s]|$)|redis://', 'Redis'),
        (r'jdbc:h2:|h2database', 'H2 Database'),
        (r'image:\s*mariadb(?:[:\s]|$)|mariadb://', 'MariaDB'),
    ]:
        if re.search(pattern, config_blob):
            p = next((p.name for p, txt in config_texts if re.search(pattern, txt.lower())), 'arquivo de configuração')
            add('Banco/Cache', tech, p, 'Alta')

    docker_files = [p for p in paths if p.name.lower() == 'dockerfile']
    compose_files = [p for p in paths if p.name.lower() in {'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml'}]
    if docker_files or compose_files:
        add('Infraestrutura', 'Docker', (docker_files or compose_files)[0].name, 'Alta')

    # Frameworks de backend Java adicionais comuns.
    java_build_text = '\n'.join(txt for name in ('pom.xml', 'build.gradle', 'build.gradle.kts') for _, txt in texts(name)).lower()
    if 'quarkus' in java_build_text: add('Backend', 'Quarkus', 'arquivo de build JVM', 'Alta')
    if 'io.micronaut' in java_build_text or 'micronaut' in java_build_text: add('Backend', 'Micronaut', 'arquivo de build JVM', 'Alta')

    return results
