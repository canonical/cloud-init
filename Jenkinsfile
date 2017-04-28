#!groovy

node {
    stage ('Checkout') {
        checkout scm
    }
    stage ('Build') {
        echo "Building branch: ${env.BRANCH_NAME}"
	sh 'make deb'
    }
    stage ('Test') {
        echo 'Testing. py27'
    }
    stage ('Deploying') {
        echo 'Deploying...'
    }
}

