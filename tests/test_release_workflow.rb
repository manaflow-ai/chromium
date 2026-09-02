#!/usr/bin/env ruby
# frozen_string_literal: true

require "yaml"

workflow_path = File.expand_path("../.github/workflows/build-chromium.yml", __dir__)
workflow = YAML.load_file(workflow_path)
validation_workflow_path = File.expand_path(
  "../.github/workflows/validate-release-workflow.yml", __dir__
)
validation_workflow = YAML.load_file(validation_workflow_path)

validation_trigger = validation_workflow.fetch(true)
%w[pull_request push].each do |event|
  paths = validation_trigger.fetch(event).fetch("paths")
  abort "#{event} validation must include the Python tool lock" unless
    paths.include?(".github/python-tools.txt")
end

trigger = workflow.fetch(true)
dispatch = trigger.fetch("workflow_dispatch")
dispatch_inputs = dispatch.fetch("inputs")
%w[source_repository source_ref source_commit release_tag].each do |name|
  definition = dispatch_inputs.fetch(name)
  abort "#{name} must be a required string input" unless
    definition.fetch("required") == true && definition.fetch("type") == "string"
  abort "#{name} must not have a policy-derived default" if definition.key?("default")
end

concurrency = workflow.fetch("concurrency")
abort "release builds must queue instead of canceling" unless
  concurrency.fetch("cancel-in-progress") == false
abort "release concurrency must be repository-scoped" unless
  concurrency.fetch("group") == "owl-chromium-${{ github.repository }}"

jobs = workflow.fetch("jobs")
build_checkout = jobs.fetch("build").fetch("steps").find do |step|
  step["name"] == "Check out reviewed artifact repository"
end
abort "build checkout step is missing" unless build_checkout
abort "build checkout must use the immutable dispatch SHA" unless
  build_checkout.fetch("with").fetch("ref") == "${{ github.sha }}"

resolve_policy = jobs.fetch("build").fetch("steps").find do |step|
  step["name"] == "Resolve reviewed build policy"
end
abort "policy resolution step is missing" unless resolve_policy
%w[--source-repository --source-ref --source-commit --release-tag].each do |option|
  abort "policy resolution must pass #{option}" unless
    resolve_policy.fetch("run").include?(option)
end

build_runner = jobs.fetch("build").fetch("runs-on")
abort "build must use the dedicated Chromium runner group" unless
  build_runner.fetch("group") == "chromium-release"
abort "build must retain the Chromium runner label" unless
  build_runner.fetch("labels") == "chromium"

publish_checkout = jobs.fetch("publish").fetch("steps").find do |step|
  step["name"] == "Check out release validators"
end
abort "publish checkout step is missing" unless publish_checkout
abort "publish checkout must use the immutable dispatch SHA" unless
  publish_checkout.fetch("with").fetch("ref") == "${{ github.sha }}"

abort "publish must use the protected chromium-release environment" unless
  jobs.fetch("publish").fetch("environment").fetch("name") == "chromium-release"
publish_step = jobs.fetch("publish").fetch("steps").find do |step|
  step["name"] == "Publish immutable release"
end
abort "publish step is missing" unless publish_step
abort "publish must validate release metadata" unless
  publish_step.fetch("run").include?("validate_release_metadata.py")
abort "publish must require a complete release asset set before promotion" unless
  publish_step.fetch("run").include?("--require-complete")

validation_jobs = validation_workflow.fetch("jobs")
validation_steps = validation_jobs.fetch("tests").fetch("steps").map do |step|
  step.fetch("run", "")
end.join("\n")
%w[ruff pyright zizmor].each do |tool|
  abort "validation workflow must run #{tool}" unless validation_steps.include?(tool)
end

puts "release workflow queue and immutable-ref policy passed"
