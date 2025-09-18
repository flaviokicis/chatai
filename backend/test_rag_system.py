#!/usr/bin/env python3
"""Comprehensive test harness for the RAG system.

This script tests the complete RAG pipeline including:
- Document parsing from various formats
- Intelligent chunking with GPT-5
- Embedding generation
- Vector storage in pgvector
- Iterative retrieval with LangGraph
- Judge assessment of relevance
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.models import Tenant, TenantProjectConfig, Flow
from app.db.session import db_session, get_engine
from app.db.base import Base
from app.services.rag import RAGService
from app.settings import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class RAGSystemTester:
    """Test harness for the RAG system."""
    
    def __init__(self):
        """Initialize the test harness."""
        self.settings = get_settings()
        self.tenant_id = None
        self.rag_service = None
        self.test_results = []
    
    async def setup(self):
        """Set up test environment."""
        logger.info("🚀 Setting up RAG system test environment...")
        
        # Initialize database tables if needed
        engine = get_engine()
        Base.metadata.create_all(engine)
        
        # Initialize RAG service
        self.rag_service = RAGService(
            openai_api_key=self.settings.openai_api_key,
            vector_db_url=self.settings.vector_database_url,
            max_retrieval_attempts=3
        )
        
        # Wait for initialization
        await asyncio.sleep(2)
        
        # Find or create test tenant
        self._setup_test_tenant()
        
        logger.info("✅ Setup complete")
    
    def _setup_test_tenant(self):
        """Find or create test tenant with luminarias flow."""
        # Use the tenant that has documents (44b613e6-c5a2-4f41-bae0-05b168245ac7)
        # This is a known tenant with chunks in the vector database
        self.tenant_id = "44b613e6-c5a2-4f41-bae0-05b168245ac7"
        
        with db_session() as session:
            # Verify tenant exists
            result = session.execute(
                text("""
                    SELECT owner_email 
                    FROM tenants 
                    WHERE id = :tenant_id
                """),
                {"tenant_id": self.tenant_id}
            )
            row = result.fetchone()
            
            if row:
                logger.info(f"Using tenant with documents: {row[0]} (ID: {self.tenant_id})")
            else:
                # Create new test tenant
                logger.info("Creating new test tenant...")
                tenant = Tenant(
                    owner_first_name="RAG",
                    owner_last_name="Tester",
                    owner_email="rag.test@chatai.com"
                )
                session.add(tenant)
                session.flush()
                
                # Add project config
                config = TenantProjectConfig(
                    tenant_id=tenant.id,
                    project_description="Empresa de iluminação LED especializada em ambientes esportivos e industriais",
                    target_audience="Gestores de facilities, engenheiros, arquitetos",
                    communication_style="Profissional, técnico mas acessível"
                )
                session.add(config)
                
                session.commit()
                self.tenant_id = tenant.id
                logger.info(f"Created test tenant: {self.tenant_id}")
    
    async def test_document_upload(self) -> Dict:
        """Test uploading documents to the RAG system."""
        logger.info("\n📄 Testing document upload...")
        
        documents_dir = Path("playground/documents/pdfs")
        test_files = [
            "catalogo_luminarias_desordenado.pdf",
            "manual_instalacao_confuso.pdf",
            "orcamento_ginasio.pdf"
        ]
        
        results = []
        
        for file_name in test_files:
            file_path = documents_dir / file_name
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue
            
            logger.info(f"Uploading: {file_name}")
            result = await self.rag_service.save_document(
                tenant_id=self.tenant_id,
                file_path=str(file_path),
                metadata={"source": "test_harness"}
            )
            
            if result['success']:
                logger.info(f"✅ {file_name}: {result['chunks_created']} chunks, {result['relationships_created']} relationships")
            else:
                logger.error(f"❌ {file_name}: {result.get('error')}")
            
            results.append(result)
        
        return {
            'test': 'document_upload',
            'total_files': len(test_files),
            'successful': sum(1 for r in results if r['success']),
            'total_chunks': sum(r.get('chunks_created', 0) for r in results),
            'details': results
        }
    
    async def test_basic_queries(self) -> List[Dict]:
        """Test basic RAG queries."""
        logger.info("\n🔍 Testing basic queries...")
        
        test_queries = [
            # === EXACT SPECIFICATION RETRIEVAL ===
            {
                'query': 'Quantos lumens tem o modelo HB-240?',
                'expected_keywords': ['36.000', 'lm', 'HB-240', 'lumens']
            },
            {
                'query': 'Qual o fluxo luminoso do SP-600?',
                'expected_keywords': ['84.000', 'lm', 'SP-600', 'fluxo']
            },
            {
                'query': 'Qual o diâmetro da luminária HB-120?',
                'expected_keywords': ['Ø340', 'mm', 'HB-120', 'dimensões']
            },
            
            # === RANGE AND THRESHOLD QUERIES ===
            {
                'query': 'Quais luminárias têm mais de 30.000 lumens?',
                'expected_keywords': ['HB-240', '36.000', 'SP-400', '56.000', 'SP-600']
            },
            {
                'query': 'Existe algum modelo com eficiência acima de 160 lm/W?',
                'expected_keywords': ['180', 'lm/W', 'HighBay', 'eficiência']
            },
            {
                'query': 'Qual produto mais leve da linha HighBay?',
                'expected_keywords': ['HB-120', '3,8', 'kg', 'leve']
            },
            
            # === APPLICATION-SPECIFIC RECOMMENDATIONS ===
            {
                'query': 'Para um centro de distribuição, qual família é indicada?',
                'expected_keywords': ['centro', 'distribuição', 'HB', 'HighBay']
            },
            {
                'query': 'Em áreas com vapores inflamáveis, qual luminária usar?',
                'expected_keywords': ['vapor', 'CP', 'Fuel', 'classificada']
            },
            {
                'query': 'Campo de futebol society precisa de qual projetor?',
                'expected_keywords': ['society', 'SP', 'Arena', 'campo']
            },
            
            # === TECHNICAL COMPLIANCE AND STANDARDS ===
            {
                'query': 'Qual o THD das luminárias HighBay?',
                'expected_keywords': ['THD', '15%', 'distorção', 'harmônica']
            },
            {
                'query': 'O fator de potência atende normas brasileiras?',
                'expected_keywords': ['0,95', 'fator', 'potência', 'PF']
            },
            {
                'query': 'Qual resistência mecânica IK dos projetores esportivos?',
                'expected_keywords': ['IK09', 'resistência', 'SP', 'mecânica']
            },
            
            # === OPTICAL AND LIGHTING CHARACTERISTICS ===
            {
                'query': 'Quais ângulos de abertura disponíveis para HB-160?',
                'expected_keywords': ['60°', '90°', 'óptica', 'ângulo']
            },
            {
                'query': 'Projetores SP têm óptica assimétrica?',
                'expected_keywords': ['assimétrica', 'simétrica', 'SP', 'óptica']
            },
            {
                'query': 'Como controlar ofuscamento em quadras?',
                'expected_keywords': ['UGR', 'visor', 'shield', 'ofuscamento']
            },
            
            # === ENVIRONMENTAL AND OPERATING CONDITIONS ===
            {
                'query': 'Qual temperatura ambiente máxima de operação?',
                'expected_keywords': ['40', '°C', 'temperatura', 'operação']
            },
            {
                'query': 'Produtos suportam temperatura negativa?',
                'expected_keywords': ['-20', '°C', 'temperatura', 'condições']
            },
            {
                'query': 'Proteção contra água e poeira da linha Canopy?',
                'expected_keywords': ['IP66', 'CP', 'água', 'poeira']
            },
            
            # === CUSTOMIZATION AND OPTIONS ===
            {
                'query': 'Posso pedir CRI maior que 80?',
                'expected_keywords': ['90', 'CRI', 'encomenda', 'opcional']
            },
            {
                'query': 'Temperatura de cor 3000K está disponível?',
                'expected_keywords': ['3000K', 'encomenda', 'CCT', 'opções']
            },
            {
                'query': 'Existem lentes secundárias de 10 graus?',
                'expected_keywords': ['10°', 'lente', 'secundária', 'acessório']
            },
            
            # === CONTROL AND AUTOMATION ===
            {
                'query': 'É possível programar perfil noturno?',
                'expected_keywords': ['programável', 'perfil', 'noturno', 'controle']
            },
            {
                'query': 'Compatibilidade com protocolo DALI?',
                'expected_keywords': ['DALI', 'protocolo', 'controle', 'dimerização']
            },
            
            # === ACCESSORIES AND MOUNTING ===
            {
                'query': 'Quais tipos de suporte para montagem existem?',
                'expected_keywords': ['U-bracket', 'pendente', 'ajustável', 'suporte']
            },
            {
                'query': 'Conectores têm proteção IP68?',
                'expected_keywords': ['IP68', 'conector', 'chicote', 'acessório']
            },
            
            # === MISSING INFORMATION (SHOULD FAIL) ===
            {
                'query': 'Qual o consumo em kWh mensal?',
                'expected_keywords': ['kWh', 'consumo', 'mensal', 'energia']
            },
            {
                'query': 'Tempo de entrega para São Paulo?',
                'expected_keywords': ['entrega', 'prazo', 'São Paulo', 'dias']
            },
            {
                'query': 'Aceita pagamento parcelado?',
                'expected_keywords': ['pagamento', 'parcela', 'cartão', 'boleto']
            }
        ]
        
        results = []
        
        for test in test_queries:
            logger.info(f"\nQuery: {test['query']}")
            
            context = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=test['query'],
                business_context={
                    'project_description': 'Empresa de iluminação LED',
                    'target_audience': 'Clientes comerciais'
                }
            )
            
            # Check if we got relevant context
            is_relevant = any(
                keyword.lower() in context.lower() 
                for keyword in test['expected_keywords']
            )
            
            if "Nothing relevant was found" in context:
                logger.warning(f"❌ No relevant context found")
                success = False
            elif is_relevant:
                logger.info(f"✅ Found relevant context ({len(context)} chars)")
                success = True
            else:
                logger.warning(f"⚠️  Context returned but may not be relevant")
                success = False
            
            results.append({
                'query': test['query'],
                'success': success,
                'context_length': len(context),
                'keywords_found': [k for k in test['expected_keywords'] if k.lower() in context.lower()]
            })
        
        return results
    
    async def test_complex_queries(self) -> List[Dict]:
        """Test complex multi-hop queries."""
        logger.info("\n🧩 Testing complex queries...")
        
        chat_history = [
            {'role': 'user', 'content': 'Preciso iluminar um ginásio'},
            {'role': 'assistant', 'content': 'Entendi que você precisa iluminar um ginásio. Posso ajudar com isso.'}
        ]
        
        complex_queries = [
            {
                'query': 'Considerando que meu ginásio tem 20x40m e 8m de altura, quantas luminárias preciso?',
                'chat_history': chat_history,
                'expected_context': 'calculation or recommendation based on dimensions'
            },
            {
                'query': 'Qual a diferença entre HIGHBAY e UFO para meu caso?',
                'chat_history': chat_history,
                'expected_context': 'comparison between product types'
            },
            {
                'query': 'Posso ter desconto para quantidade?',
                'chat_history': chat_history + [
                    {'role': 'user', 'content': 'Vou precisar de 20 luminárias'}
                ],
                'expected_context': 'pricing or discount information'
            }
        ]
        
        results = []
        
        for test in complex_queries:
            logger.info(f"\nComplex query: {test['query']}")
            
            context = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=test['query'],
                chat_history=test.get('chat_history', []),
                business_context={
                    'project_description': 'Iluminação para ambientes esportivos',
                    'communication_style': 'Técnico e consultivo'
                }
            )
            
            success = "Nothing relevant was found" not in context
            
            if success:
                logger.info(f"✅ Retrieved context for complex query")
            else:
                logger.warning(f"❌ Failed to retrieve relevant context")
            
            results.append({
                'query': test['query'],
                'success': success,
                'context_length': len(context) if context else 0,
                'has_chat_history': bool(test.get('chat_history'))
            })
        
        return results
    
    async def test_retrieval_loop(self) -> Dict:
        """Test the iterative retrieval loop."""
        logger.info("\n🔄 Testing retrieval loop...")
        
        # Query that might require multiple attempts
        difficult_query = "Qual o consumo energético mensal de uma instalação com 50 luminárias?"
        
        # Track retrieval sessions
        stats_before = await self.rag_service.get_tenant_stats(self.tenant_id)
        
        context = await self.rag_service.query(
            tenant_id=self.tenant_id,
            query=difficult_query
        )
        
        # Check if retrieval happened
        stats_after = await self.rag_service.get_tenant_stats(self.tenant_id)
        
        return {
            'test': 'retrieval_loop',
            'query': difficult_query,
            'context_retrieved': "Nothing relevant was found" not in context,
            'context_length': len(context) if context else 0,
            'tenant_has_docs': stats_after['has_documents'],
            'total_chunks': stats_after['total_chunks']
        }
    
    async def test_edge_cases(self) -> List[Dict]:
        """Test edge cases and error handling."""
        logger.info("\n⚠️  Testing edge cases...")
        
        results = []
        
        # Test 1: Empty query
        logger.info("Testing empty query...")
        try:
            context = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=""
            )
            results.append({
                'case': 'empty_query',
                'handled': True,
                'result': 'returned context or error'
            })
        except Exception as e:
            results.append({
                'case': 'empty_query',
                'handled': False,
                'error': str(e)
            })
        
        # Test 2: Very long query
        logger.info("Testing very long query...")
        long_query = "Preciso de informações sobre " + " ".join(["luminárias"] * 500)
        try:
            context = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=long_query
            )
            results.append({
                'case': 'long_query',
                'handled': True,
                'truncated': len(context) < len(long_query)
            })
        except Exception as e:
            results.append({
                'case': 'long_query',
                'handled': False,
                'error': str(e)
            })
        
        # Test 3: Special characters
        logger.info("Testing special characters...")
        special_query = "Preço da luminária <script>alert('test')</script> em R$"
        try:
            context = await self.rag_service.query(
                tenant_id=self.tenant_id,
                query=special_query
            )
            results.append({
                'case': 'special_characters',
                'handled': True,
                'sanitized': '<script>' not in context
            })
        except Exception as e:
            results.append({
                'case': 'special_characters',
                'handled': False,
                'error': str(e)
            })
        
        return results
    
    async def run_all_tests(self):
        """Run all tests and generate report."""
        logger.info("\n" + "="*60)
        logger.info("🧪 STARTING RAG SYSTEM COMPREHENSIVE TEST SUITE")
        logger.info("="*60)
        
        try:
            # Setup
            await self.setup()
            
            # Check if documents exist
            has_docs = await self.rag_service.has_documents(self.tenant_id)
            
            # Upload documents if needed
            if not has_docs:
                upload_results = await self.test_document_upload()
                self.test_results.append(upload_results)
            else:
                logger.info("ℹ️  Tenant already has documents, skipping upload")
            
            # Run query tests
            basic_results = await self.test_basic_queries()
            self.test_results.append({
                'test': 'basic_queries',
                'total': len(basic_results),
                'successful': sum(1 for r in basic_results if r['success']),
                'details': basic_results
            })
            
            complex_results = await self.test_complex_queries()
            self.test_results.append({
                'test': 'complex_queries',
                'total': len(complex_results),
                'successful': sum(1 for r in complex_results if r['success']),
                'details': complex_results
            })
            
            loop_results = await self.test_retrieval_loop()
            self.test_results.append(loop_results)
            
            edge_results = await self.test_edge_cases()
            self.test_results.append({
                'test': 'edge_cases',
                'total': len(edge_results),
                'handled': sum(1 for r in edge_results if r.get('handled')),
                'details': edge_results
            })
            
            # Generate report
            self._generate_report()
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}", exc_info=True)
        finally:
            if self.rag_service:
                await self.rag_service.close()
    
    def _generate_report(self):
        """Generate test report."""
        logger.info("\n" + "="*60)
        logger.info("📊 RAG SYSTEM TEST REPORT")
        logger.info("="*60)
        
        for result in self.test_results:
            test_name = result.get('test', 'unknown')
            logger.info(f"\n### {test_name.upper().replace('_', ' ')}")
            
            if test_name == 'document_upload':
                logger.info(f"Files: {result.get('successful')}/{result.get('total_files')}")
                logger.info(f"Total chunks created: {result.get('total_chunks')}")
            
            elif test_name in ['basic_queries', 'complex_queries']:
                logger.info(f"Queries: {result.get('successful')}/{result.get('total')}")
                success_rate = (result.get('successful', 0) / result.get('total', 1)) * 100
                logger.info(f"Success rate: {success_rate:.1f}%")
            
            elif test_name == 'retrieval_loop':
                logger.info(f"Context retrieved: {result.get('context_retrieved')}")
                logger.info(f"Total chunks available: {result.get('total_chunks')}")
            
            elif test_name == 'edge_cases':
                logger.info(f"Cases handled: {result.get('handled')}/{result.get('total')}")
        
        # Overall summary
        logger.info("\n" + "="*60)
        logger.info("✅ RAG SYSTEM TEST SUITE COMPLETED")
        logger.info("="*60)
        
        # Save results to file
        output_file = Path("rag_test_results.json")
        with open(output_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        logger.info(f"\nDetailed results saved to: {output_file}")


async def main():
    """Main entry point."""
    tester = RAGSystemTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
