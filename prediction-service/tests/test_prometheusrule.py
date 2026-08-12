import os
import unittest
import yaml


class TestPrometheusRuleYAML(unittest.TestCase):

    def setUp(self):
        # Locate the prometheusrule manifest
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.yaml_path = os.path.abspath(
            os.path.join(current_dir, "../../kubernetes/manifests/kubeguard-prometheusrule.yaml")
        )

    def test_yaml_syntax_and_structure(self):
        """Verify the PrometheusRule YAML file parses and matches CRD spec."""
        self.assertTrue(os.path.exists(self.yaml_path), f"File {self.yaml_path} does not exist.")

        with open(self.yaml_path, "r") as f:
            data = yaml.safe_load(f)

        # 1. Verify resource type and metadata namespaces
        self.assertEqual(data.get("apiVersion"), "monitoring.coreos.com/v1")
        self.assertEqual(data.get("kind"), "PrometheusRule")
        
        metadata = data.get("metadata", {})
        self.assertEqual(metadata.get("name"), "kubeguard-rules")
        self.assertEqual(metadata.get("namespace"), "kubeguard")
        
        labels = metadata.get("labels", {})
        self.assertEqual(labels.get("release"), "kube-prometheus-stack")

        # 2. Verify rules group exist
        spec = data.get("spec", {})
        groups = spec.get("groups", [])
        self.assertEqual(len(groups), 1)
        
        group = groups[0]
        self.assertEqual(group.get("name"), "kubeguard.rules")
        
        rules = group.get("rules", [])
        self.assertEqual(len(rules), 5)

        # 3. Verify each rule properties
        alert_names = [rule.get("alert") for rule in rules]
        expected_alerts = [
            "KubeGuardHighRiskPod",
            "KubeGuardPodAnomaly",
            "KubeGuardMemoryGrowth",
            "KubeGuardCPUTrend",
            "KubeGuardPodRestart"
        ]
        self.assertCountEqual(alert_names, expected_alerts)

        # Validate specifics for each rule
        for rule in rules:
            alert = rule.get("alert")
            expr = rule.get("expr")
            duration = rule.get("for")
            labels = rule.get("labels", {})
            annotations = rule.get("annotations", {})

            self.assertIsNotNone(expr, f"Alert {alert} is missing expression.")
            self.assertEqual(duration, "2m")
            self.assertEqual(labels.get("severity"), "critical")
            
            self.assertIn("summary", annotations)
            self.assertIn("description", annotations)
            
            desc = annotations.get("description")
            self.assertIn("{{ $labels.exported_pod }}", desc)
            self.assertIn("{{ $labels.exported_namespace }}", desc)

            # Match expression details
            if alert == "KubeGuardHighRiskPod":
                self.assertEqual(expr, "kubeguard_pod_risk_score >= 60")
            elif alert == "KubeGuardPodAnomaly":
                self.assertEqual(expr, "kubeguard_pod_anomaly == 1")
            elif alert == "KubeGuardMemoryGrowth":
                self.assertEqual(expr, "kubeguard_pod_memory_trend_bytes_per_second > 1000")
            elif alert == "KubeGuardCPUTrend":
                self.assertEqual(expr, "kubeguard_pod_cpu_trend > 0.0001")
            elif alert == "KubeGuardPodRestart":
                self.assertEqual(expr, "kubeguard_pod_restart_count >= 4")


if __name__ == "__main__":
    unittest.main()
