# extract bash completion
_extract_completions() {
    local cur prev opts
    COMPREPLY=(); cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="-v --verbose -l --list -f --force -d --directory -C -n --dry-run -t --test --check -i --info -r --recursive -p --password --cat --view -o --open --json --keep-junk --no-flatten --notify --insecure -j --jobs --parallel --tui -c --create --pack -q --quiet --no-color --sha256 --verify --copy-path --max-size --max-file-size --max-files --max-ratio --max-depth --include --search --grep --strict --no-exec --allow-symlinks --preserve-perms --sandbox --delete-nested --on-error --version --help"
    [[ ${cur} == -* ]] && { COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) ); return 0; }
    COMPREPLY=( $(compgen -f -X '!*.@(tar|tgz|tar.gz|tbz2|tar.bz2|txz|tar.xz|tzst|tar.zst|zip|7z|rar|bz2|gz|xz|zst|br|lz4|deb|rpm|iso|jar|war|apk|epub|docx|xlsx|pptx|cbz|cbr|xapk|dmg)' -- ${cur}) )
}
complete -F _extract_completions extract x

