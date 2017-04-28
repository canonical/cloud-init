#!groovy

node {
    stage ('Checkout') {
        checkout scm
    }
    stage ('Build') {
        echo 'Building branch: ${env.BRANCH_NAME}'
    }
    stage ('Test') {
        echo 'Testing...'
    }
    stage ('Deploying') {
        echo 'Deploying...'
    }
}

