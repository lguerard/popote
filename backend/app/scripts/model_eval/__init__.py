"""Évaluation d'un modèle Ollama sur les tâches de Popote.

Point d'entrée : ``python -m app.scripts.model_eval --model <modèle>``,
lancé dans le conteneur backend par la veille des modèles du serveur
(server_setup/model-watch, via ``docker exec``) — c'est elle qui découvre,
télécharge et compare les modèles ; Popote ne fait que noter un modèle donné
sur SES tâches, avec SES prompts, requêtes et analyseurs de production.

Voir cases.py (d'où viennent les cas), scoring.py (comment ils sont notés)
et runner.py (comment ils sont passés au modèle).
"""
