complete -c extract -s v -l verbose
complete -c extract -s l -l list
complete -c extract -s f -l force
complete -c extract -s n -l dry-run
complete -c extract -s t -l test
complete -c extract -s i -l info
complete -c extract -s r -l recursive
complete -c extract -s o -l open
complete -c extract -l json
complete -c extract -s q -l quiet
complete -c extract -l tui
complete -c extract -l version
complete -c extract -f -a "(__fish_complete_suffix .zip .tar .tar.gz .tgz .7z .rar .gz .xz .bz2 .zst)"
complete -c x -w extract

